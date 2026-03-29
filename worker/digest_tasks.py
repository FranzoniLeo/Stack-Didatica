"""
Tarefa periódica: todo dia às 10:00 (fuso DIGEST_TZ) envia e-mail com consultas do dia anterior.

Agendamento definido em worker.celery_app (Celery Beat).
"""
from __future__ import annotations

import logging
import os

from worker.celery_app import DIGEST_TZ, celery_app
from worker.consultation_log import ConsultationRow, fetch_consultations_grouped_for_yesterday
from worker.email_outbound import smtp_configured, send_plain_email
from worker.recipients import get_digest_email

logger = logging.getLogger(__name__)

# Aviso quando a rotina corre mas não há linhas no digest para o dia de relatório
DIGEST_EMPTY_RUN_NOTIFY_TO = "leonardo.franzoni@bix-tech.com"


def _format_body(user_id: str, report_date, rows: list[ConsultationRow]) -> str:
    lines = [
        f"Olá,",
        f"",
        f"Resumo das suas consultas (par/ímpar) em {report_date.isoformat()}:",
        f"Identificador na aplicação: {user_id}",
        f"",
    ]
    for r in rows:
        lines.append(f"  • Número {r.number} → {r.result} (job {r.job_id})")
    lines.append("")
    lines.append("— Sistema de notificação automática")
    return "\n".join(lines)


@celery_app.task(name="worker.digest_tasks.send_yesterday_digest")
def send_yesterday_digest() -> dict:
    """
    Agrupa consultas gravadas no dia anterior (no fuso DIGEST_TZ) e tenta enviar um e-mail por utilizador.
    Se não houver linhas, envia um aviso para DIGEST_EMPTY_RUN_NOTIFY_TO de que a rotina correu.
    """
    by_user, report_date = fetch_consultations_grouped_for_yesterday(DIGEST_TZ)
    sent = 0
    skipped_no_email = 0
    skipped_no_smtp = 0
    errors = 0
    empty_run_notification_sent = False

    if not by_user:
        logger.info("Digest: nenhuma consulta no dia %s", report_date)
        smtp_ok = smtp_configured()
        if not smtp_ok:
            skipped_no_smtp = 1
            logger.warning(
                "Digest: SMTP não configurado; não enviado aviso de rotina sem dados"
            )
        else:
            subject = f"[Digest] Rotina executada — sem dados para {report_date.isoformat()}"
            tz_label = os.environ.get("DIGEST_TZ", DIGEST_TZ)
            body = (
                f"A rotina diária de resumo de consultas foi executada.\n\n"
                f"Não há consultas registadas para o dia {report_date.isoformat()} "
                f"(fuso {tz_label}).\n\n"
                f"— Sistema de notificação automática"
            )
            try:
                send_plain_email(
                    to_addr=DIGEST_EMPTY_RUN_NOTIFY_TO,
                    subject=subject,
                    body=body,
                )
                empty_run_notification_sent = True
                logger.info(
                    "Digest: aviso de rotina sem dados enviado para %s",
                    DIGEST_EMPTY_RUN_NOTIFY_TO,
                )
            except Exception:
                errors += 1
                logger.exception(
                    "Digest: falha ao enviar aviso de rotina sem dados para %s",
                    DIGEST_EMPTY_RUN_NOTIFY_TO,
                )
        return {
            "report_date": report_date.isoformat(),
            "timezone": os.environ.get("DIGEST_TZ", DIGEST_TZ),
            "users_with_rows": 0,
            "emails_sent": 0,
            "skipped_no_email": 0,
            "skipped_smtp": skipped_no_smtp,
            "errors": errors,
            "empty_run_notification_sent": empty_run_notification_sent,
        }

    smtp_ok = smtp_configured()

    for user_id, rows in by_user.items():
        to_addr = get_digest_email(user_id)
        if not to_addr:
            skipped_no_email += 1
            logger.info("Digest: usuário %s — sem e-mail configurado (stub), ignorando envio", user_id)
            continue
        if not smtp_ok:
            skipped_no_smtp += 1
            logger.warning("Digest: SMTP não configurado; não enviado para %s", to_addr)
            continue
        subject = f"Suas consultas de {report_date.isoformat()}"
        body = _format_body(user_id, report_date, rows)
        try:
            send_plain_email(to_addr=to_addr, subject=subject, body=body)
            sent += 1
            logger.info("Digest: enviado para %s (%d linhas)", to_addr, len(rows))
        except Exception:
            errors += 1
            logger.exception("Digest: falha ao enviar para %s", to_addr)

    return {
        "report_date": report_date.isoformat(),
        "timezone": os.environ.get("DIGEST_TZ", DIGEST_TZ),
        "users_with_rows": len(by_user),
        "emails_sent": sent,
        "skipped_no_email": skipped_no_email,
        "skipped_smtp": skipped_no_smtp,
        "errors": errors,
        "empty_run_notification_sent": False,
    }
