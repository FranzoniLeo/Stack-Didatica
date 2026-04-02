"""Endpoints de administração: DLQ (lista e reprocessamento)."""
import uuid as uuid_stdlib

from fastapi import APIRouter, Depends, HTTPException

from main_server.auth_core import require_admin
from main_server.models import User
from main_server.schemas import DlqReprocessBody
from worker.dlq import list_dlq_entries, peek_dlq_entry, reappend_dlq_raw, remove_dlq_raw_line
from worker.job_store import create, delete_job_orphan, try_bind_consultation_to_job
from worker.tasks import process_even_odd

router = APIRouter(prefix="/admin/dlq", tags=["admin-dlq"])


@router.get("")
def admin_list_dlq(_admin: User = Depends(require_admin)):
    entries = list_dlq_entries()
    return {"count": len(entries), "entries": entries}


@router.post("/reprocess")
def admin_reprocess_dlq(
    body: DlqReprocessBody,
    _admin: User = Depends(require_admin),
):
    """
    Tira uma entrada da DLQ e enfileira novo processamento (novo job_id / consultation_id).
    Use `dlq_entry_id` (preferido) ou `job_id` de registos antigos sem id.
    """
    eid = (body.dlq_entry_id or "").strip() or None
    jid = (body.job_id or "").strip() or None

    found = peek_dlq_entry(
        dlq_entry_id=eid,
        legacy_job_id=jid if not eid else None,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Entrada não encontrada na DLQ")

    entry, raw_line = found
    user_id = entry.get("user_id")
    number = entry.get("number")
    if user_id is None or number is None:
        raise HTTPException(status_code=400, detail="Entrada DLQ inválida: falta user_id ou number")
    try:
        num = int(number)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Número inválido na entrada DLQ")

    uid = str(user_id).strip()
    cid = str(uuid_stdlib.uuid4())

    if remove_dlq_raw_line(raw_line) != 1:
        raise HTTPException(status_code=409, detail="Entrada já foi removida; tente de novo.")

    try:
        job_id = create(num, uid, consultation_id=cid)
        if not try_bind_consultation_to_job(uid, cid, job_id):
            delete_job_orphan(job_id)
            raise HTTPException(
                status_code=409,
                detail="Conflito de idempotência ao recriar job; entrada reposta na DLQ.",
            )
        process_even_odd.delay(job_id, num)
    except HTTPException:
        reappend_dlq_raw(raw_line)
        raise
    except Exception:
        reappend_dlq_raw(raw_line)
        raise

    return {
        "message": "Reprocessamento enfileirado.",
        "new_job_id": job_id,
        "consultation_id": cid,
        "previous_failed_job_id": entry.get("job_id"),
        "removed_dlq_entry_id": entry.get("dlq_entry_id"),
    }
