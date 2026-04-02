import logging
import os

import httpx

from worker.celery_app import celery_app
from worker.consultation_log import log_completed_consultation
from worker.dlq import record_dead_letter
from worker.job_store import get as get_job
from worker.job_store import reset_for_retry
from worker.job_store import set_cached_result_for_user_number
from worker.job_store import set_completed, set_failed, set_running

logger = logging.getLogger(__name__)

MOCK_SERVER_URL = os.environ.get("MOCK_SERVER_URL", "http://127.0.0.1:8001").rstrip("/")
TIMEOUT = 40
MAX_RETRIES = int(os.environ.get("JOB_TASK_MAX_RETRIES", "3"))
RETRY_COUNTDOWN = float(os.environ.get("JOB_RETRY_COUNTDOWN", "10"))


@celery_app.task(bind=True, max_retries=MAX_RETRIES)
def process_even_odd(self, job_id: str, number: int) -> None:
    set_running(job_id)
    url = f"{MOCK_SERVER_URL}/even-odd/{number}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(url)
            response.raise_for_status()
            result = response.json()
        set_completed(job_id, result)
        job = get_job(job_id)
        uid = job.get("user_id") if job else None
        if uid:
            # Cache de resultados para evitar processamento desnecessário
            set_cached_result_for_user_number(user_id=str(uid), number=number, result=result)
            log_completed_consultation(
                user_external_id=str(uid),
                number=number,
                result=str(result.get("result", "")),
                job_id=job_id,
            )
    except Exception as e:
        attempt = self.request.retries + 1
        max_attempts = self.max_retries + 1
        if self.request.retries >= self.max_retries:
            set_failed(
                job_id,
                "O processo falhou após o número máximo de tentativas.",
            )
            job_row = get_job(job_id)
            record_dead_letter(
                job_id=job_id,
                number=number,
                user_id=(job_row.get("user_id") if job_row else None),
                attempts=attempt,
                mock_url=url,
                exception=e,
            )
            logger.exception(
                "Job %s falhou após %s tentativa(s): %s",
                job_id,
                attempt,
                e,
            )
            raise
        reset_for_retry(
            job_id,
            status_message=f"Erro ao processar requisição, tentativa: {attempt}",
        )
        logger.warning(
            "Job %s erro (tentativa %s/%s), reenfileirando: %s",
            job_id,
            attempt,
            max_attempts,
            e,
        )
        raise self.retry(exc=e, countdown=RETRY_COUNTDOWN)
