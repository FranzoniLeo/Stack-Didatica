from fastapi import APIRouter, Depends, HTTPException, Query

from main_server.auth_core import get_current_user
from main_server.models import User
from worker.consultation_log import delete_all_consultations_for_user
from worker.job_store import (
    create,
    delete_all_for_user,
    delete_number_cache_for_user,
    get,
    get_cached_result_for_user_number,
    list_by_user,
)
from worker.tasks import process_even_odd

router = APIRouter()


@router.post("/consultar")
async def submit_consultar(
    number: int = Query(..., description="Número para verificar par/ímpar"),
    current_user: User = Depends(get_current_user),
):
    """Envia uma consulta para o worker (usuário vem do token JWT)."""
    uid = str(current_user.id)
    cached = get_cached_result_for_user_number(uid, number)
    job_id = create(number, uid)
    if cached is not None:
        # Mantém o contrato do front (job_id + polling) sem chamar o mock.
        from worker.job_store import set_completed  # import local evita ciclo em alguns ambientes

        set_completed(job_id, cached)
    else:
        process_even_odd.delay(job_id, number)
    return {
        "job_id": job_id,
        "user_id": uid,
        "status": "pending",
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
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
        "elapsed_seconds": elapsed,
    }


@router.get("/me/jobs")
def get_my_jobs(current_user: User = Depends(get_current_user)):
    """Lista jobs no Redis do usuário logado."""
    uid = str(current_user.id)
    jobs = list_by_user(uid)
    return {"user_id": uid, "count": len(jobs), "jobs": jobs}


@router.delete("/me/jobs")
def clear_my_consultation_history(current_user: User = Depends(get_current_user)):
    """Remove todo o histórico de consultas do utilizador (Redis + registo do digest, se configurado)."""
    uid = str(current_user.id)
    removed_jobs = delete_all_for_user(uid)
    removed_number_cache = delete_number_cache_for_user(uid)
    removed_digest = delete_all_consultations_for_user(uid)
    return {
        "message": "Histórico limpo.",
        "removed_jobs": removed_jobs,
        "removed_number_cache": removed_number_cache,
        "removed_digest_rows": removed_digest,
    }
