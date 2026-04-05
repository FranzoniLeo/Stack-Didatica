import uuid as uuid_stdlib
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query

from main_server.auth_core import get_current_user
from main_server.models import User
from worker.consultation_log import delete_all_consultations_for_user
from worker.job_store import (
    create,
    delete_all_for_user,
    delete_idempotency_key,
    delete_idempotency_keys_for_user,
    delete_job_orphan,
    delete_number_cache_for_user,
    get,
    get_cached_result_for_user_number,
    get_job_id_for_consultation,
    list_by_user,
    try_bind_consultation_to_job,
)
from worker.tasks import process_even_odd

router = APIRouter()


class JobsParityFilter(str, Enum):
    all = "all"
    even = "even"
    odd = "odd"


def _normalize_consultation_id(raw: str | None) -> str:
    if raw is None or not str(raw).strip():
        return str(uuid_stdlib.uuid4())
    try:
        return str(uuid_stdlib.UUID(str(raw).strip()))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="consultation_id inválido: use um UUID v4 ou omita para gerar um novo.",
        )


@router.post("/consultar")
async def submit_consultar(
    number: int = Query(..., description="Número para verificar par/ímpar"),
    consultation_id: str | None = Query(
        None,
        description="UUID da consulta (Omita para o servidor gerar um novo)",
    ),
    current_user: User = Depends(get_current_user),
):
    """Envia uma consulta para o worker (usuário vem do token JWT)."""
    uid = str(current_user.id)
    cid = _normalize_consultation_id(consultation_id)

    """ Verifica se a consulta já foi enviada com este ID de consulta. """
    existing_job_id = get_job_id_for_consultation(uid, cid)
    if existing_job_id:
        existing_job = get(existing_job_id)
        if existing_job is None:
            delete_idempotency_key(uid, cid)
        else:
            return {
                "job_id": existing_job_id,
                "user_id": uid,
                "consultation_id": cid,
                "status": existing_job.get("status", "pending"),
                "deduplicated": True,
                "message": "Consulta já registrada com este ID; nenhum processamento duplicado.",
            }

    """ caso não tenha sido enviada, cria o job e tenta vincular o ID de consulta ao job. """
    cached = get_cached_result_for_user_number(uid, number)
    job_id = create(number, uid, consultation_id=cid)
    if not try_bind_consultation_to_job(uid, cid, job_id):
        delete_job_orphan(job_id)
        winner = get_job_id_for_consultation(uid, cid)
        if not winner:
            raise HTTPException(status_code=409, detail="Idempotência em conflito; tente novamente.")
        job = get(winner)
        if job is None:
            raise HTTPException(status_code=409, detail="Estado inconsistente; tente novamente.")
        return {
            "job_id": winner,
            "user_id": uid,
            "consultation_id": cid,
            "status": job.get("status", "pending"),
            "deduplicated": True,
            "message": "Consulta já registrada com este ID; nenhum processamento duplicado.",
        }

    """ caso a consulta já tenha sido processada, retorna o resultado. """
    if cached is not None:
        from worker.job_store import set_completed

        set_completed(job_id, cached)
    else:
        process_even_odd.delay(job_id, number)
    return {
        "job_id": job_id,
        "user_id": uid,
        "consultation_id": cid,
        "status": "pending",
        "deduplicated": False,
        "message": "Consulta enviada. Você pode fechar a página e voltar depois.",
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Status do job (somente o dono)."""
    job = get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=404, detail="Job não encontrado")
    elapsed = None
    if job.get("completed_at") and job.get("created_at"):
        elapsed = round(job["completed_at"] - job["created_at"], 1)
    return {
        "job_id": job["id"],
        "user_id": job.get("user_id"),
        "number": job["number"],
        "consultation_id": job.get("consultation_id"),
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
        "status_message": job.get("status_message"),
        "elapsed_seconds": elapsed,
    }


@router.get("/me/jobs")
def get_my_jobs(
    parity: JobsParityFilter = Query(
        JobsParityFilter.all,
        description=(
            "Filtro pelo resultado salvo (result.result em jobs completed): "
            "all, even (rótulo par), odd (rótulo ímpar)."
        ),
    ),
    current_user: User = Depends(get_current_user),
):
    """Lista jobs do utilizador; even/odd restricto a completed com resultado persistido."""
    uid = str(current_user.id)
    jobs = list_by_user(uid, parity=parity.value)
    return {
        "user_id": uid,
        "parity": parity.value,
        "count": len(jobs),
        "jobs": jobs,
    }


@router.delete("/me/jobs")
def clear_my_consultation_history(current_user: User = Depends(get_current_user)):
    """Remove todo o histórico de consultas do utilizador (Redis + registo do digest, se configurado)."""
    uid = str(current_user.id)
    removed_jobs = delete_all_for_user(uid)
    removed_number_cache = delete_number_cache_for_user(uid)
    removed_idempotency = delete_idempotency_keys_for_user(uid)
    removed_digest = delete_all_consultations_for_user(uid)
    return {
        "message": "Histórico limpo.",
        "removed_jobs": removed_jobs,
        "removed_number_cache": removed_number_cache,
        "removed_idempotency_keys": removed_idempotency,
        "removed_digest_rows": removed_digest,
    }
