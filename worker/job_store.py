import json
import os
import time
import uuid

import redis
from pymongo import MongoClient

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB", "email_notification")

USER_NUM_PREFIX = "user_num:"
IDEMP_PREFIX = "idemp:"
# Redis TTL só para idempotência e cache numérico (jobs no Mongo).
REDIS_AUX_TTL_SECONDS = 86400

_mongo: MongoClient | None = None
_job_indexes_ready = False


def _redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def _mongo_client() -> MongoClient:
    global _mongo
    if _mongo is None:
        _mongo = MongoClient(MONGODB_URL)
    return _mongo


def _jobs_coll():
    coll = _mongo_client()[MONGODB_DB_NAME]["jobs"]
    global _job_indexes_ready
    if not _job_indexes_ready:
        coll.create_index("id", unique=True)
        coll.create_index([("user_id", 1), ("created_at", -1)])
        _job_indexes_ready = True
    return coll


def _doc_to_job(doc: dict | None) -> dict | None:
    if not doc:
        return None
    out = dict(doc)
    out.pop("_id", None)
    return out


def create(number: int, user_id: str, *, consultation_id: str | None = None) -> str:
    job_id = uuid.uuid4().hex[:12]
    normalized_user_id = user_id.strip()
    job = {
        "id": job_id,
        "user_id": normalized_user_id,
        "number": number,
        "consultation_id": consultation_id,
        "status": "pending",
        "result": None,
        "error": None,
        "status_message": None,
        "created_at": time.time(),
        "completed_at": None,
    }
    _jobs_coll().insert_one(job)
    return job_id


def set_running(job_id: str) -> None:
    _jobs_coll().update_one(
        {"id": job_id},
        {"$set": {"status": "running", "status_message": None}},
    )


def set_completed(job_id: str, result: dict) -> None:
    _jobs_coll().update_one(
        {"id": job_id},
        {
            "$set": {
                "status": "completed",
                "result": result,
                "completed_at": time.time(),
                "status_message": None,
            }
        },
    )


def set_failed(job_id: str, error: str) -> None:
    _jobs_coll().update_one(
        {"id": job_id},
        {
            "$set": {
                "status": "failed",
                "error": error,
                "completed_at": time.time(),
                "status_message": None,
            }
        },
    )

""" Reprocessamento de jobs com falha """
def reset_for_retry(job_id: str, *, status_message: str) -> None:
    """Volta o job para pending antes de reenfileirar; guarda mensagem amigável para o cliente (polling)."""
    _jobs_coll().update_one(
        {"id": job_id},
        {
            "$set": {
                "status": "pending",
                "error": None,
                "completed_at": None,
                "status_message": status_message,
            }
        },
    )


def get(job_id: str) -> dict | None:
    return _doc_to_job(_jobs_coll().find_one({"id": job_id}))


def list_by_user(user_id: str, *, parity: str = "all") -> list[dict]:
    """parity: all | even | odd.

    Para even/odd filtra apenas jobs ``completed`` pelo rótulo persistido em
    ``result.result`` (ex.: \"par\" / \"ímpar\").
    """
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return []
    filt: dict = {"user_id": normalized_user_id}
    if parity == "even":
        filt["status"] = "completed"
        filt["result.result"] = "par"
    elif parity == "odd":
        filt["status"] = "completed"
        filt["result.result"] = "ímpar"
    cursor = _jobs_coll().find(filt).sort("created_at", -1)
    return [_doc_to_job(d) for d in cursor if d]


def get_job_id_for_consultation(user_id: str, consultation_id: str) -> str | None:
    r = _redis()
    uid = user_id.strip()
    cid = consultation_id.strip()
    if not uid or not cid:
        return None
    return r.get(f"{IDEMP_PREFIX}{uid}:{cid}")


def try_bind_consultation_to_job(user_id: str, consultation_id: str, job_id: str) -> bool:
    """Reserva idempotência (SET NX). True se este job_id ficou associado ao consultation_id."""
    r = _redis()
    uid = user_id.strip()
    cid = consultation_id.strip()
    if not uid or not cid:
        return False
    return bool(
        r.set(
            f"{IDEMP_PREFIX}{uid}:{cid}",
            job_id,
            nx=True,
            ex=REDIS_AUX_TTL_SECONDS,
        )
    )


def delete_job_orphan(job_id: str) -> None:
    """Remove job (Mongo). Idempotência Redis não é limpa aqui — outro pedido já venceu o SET NX."""
    _jobs_coll().delete_one({"id": job_id})


def delete_idempotency_keys_for_user(user_id: str) -> int:
    """Apaga idemp:{uid}:* (ex.: ao limpar histórico)."""
    r = _redis()
    uid = user_id.strip()
    if not uid:
        return 0
    pattern = f"{IDEMP_PREFIX}{uid}:*"
    keys = list(r.scan_iter(match=pattern, count=500))
    if not keys:
        return 0
    pipe = r.pipeline(transaction=False)
    for k in keys:
        pipe.delete(k)
    pipe.execute()
    return len(keys)


def delete_idempotency_key(user_id: str, consultation_id: str) -> None:
    r = _redis()
    uid = user_id.strip()
    cid = consultation_id.strip()
    if uid and cid:
        r.delete(f"{IDEMP_PREFIX}{uid}:{cid}")


""" Cache de valores já consultados para evitar processamento desnecessário """
def get_cached_result_for_user_number(user_id: str, number: int) -> dict | None:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return None
    r = _redis()
    data = r.get(f"{USER_NUM_PREFIX}{normalized_user_id}:{number}")
    if not data:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def set_cached_result_for_user_number(*, user_id: str, number: int, result: dict) -> None:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return
    r = _redis()
    r.set(
        f"{USER_NUM_PREFIX}{normalized_user_id}:{number}",
        json.dumps(result),
        ex=REDIS_AUX_TTL_SECONDS,
    )


def delete_number_cache_for_user(user_id: str) -> int:
    """Apaga o cache user_num:{uid}:* (dedupe por número). Retorna quantas chaves foram removidas."""
    r = _redis()
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return 0
    pattern = f"{USER_NUM_PREFIX}{normalized_user_id}:*"
    keys = list(r.scan_iter(match=pattern, count=500))
    if not keys:
        return 0
    pipe = r.pipeline(transaction=False)
    for k in keys:
        pipe.delete(k)
    pipe.execute()
    return len(keys)


def delete_all_for_user(user_id: str) -> int:
    """Remove todos os jobs (Mongo) do utilizador. Retorna quantos documentos foram apagados."""
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return 0
    result = _jobs_coll().delete_many({"user_id": normalized_user_id})
    return int(result.deleted_count)
