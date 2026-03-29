import json
import os
import time
import uuid

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
KEY_PREFIX = "job:"
USER_JOBS_PREFIX = "user_jobs:"
USER_NUM_PREFIX = "user_num:"
JOB_TTL_SECONDS = 86400


def _client() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def create(number: int, user_id: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    normalized_user_id = user_id.strip()
    job = {
        "id": job_id,
        "user_id": normalized_user_id,
        "number": number,
        "status": "pending",
        "result": None,
        "error": None,
        "created_at": time.time(),
        "completed_at": None,
    }
    client = _client()
    job_key = f"{KEY_PREFIX}{job_id}"
    user_jobs_key = f"{USER_JOBS_PREFIX}{normalized_user_id}"
    client.set(job_key, json.dumps(job), ex=JOB_TTL_SECONDS)
    client.sadd(user_jobs_key, job_id)
    client.expire(user_jobs_key, JOB_TTL_SECONDS)
    return job_id


def set_running(job_id: str) -> None:
    client = _client()
    key = f"{KEY_PREFIX}{job_id}"
    data = client.get(key)
    if data:
        job = json.loads(data)
        job["status"] = "running"
        client.set(key, json.dumps(job), ex=JOB_TTL_SECONDS)


def set_completed(job_id: str, result: dict) -> None:
    client = _client()
    key = f"{KEY_PREFIX}{job_id}"
    data = client.get(key)
    if data:
        job = json.loads(data)
        job["status"] = "completed"
        job["result"] = result
        job["completed_at"] = time.time()
        client.set(key, json.dumps(job), ex=JOB_TTL_SECONDS)


def set_failed(job_id: str, error: str) -> None:
    client = _client()
    key = f"{KEY_PREFIX}{job_id}"
    data = client.get(key)
    if data:
        job = json.loads(data)
        job["status"] = "failed"
        job["error"] = error
        job["completed_at"] = time.time()
        client.set(key, json.dumps(job), ex=JOB_TTL_SECONDS)


def reset_for_retry(job_id: str) -> None:
    """Volta o job para pending antes de reenfileirar (evita mostrar failed entre tentativas)."""
    client = _client()
    key = f"{KEY_PREFIX}{job_id}"
    data = client.get(key)
    if data:
        job = json.loads(data)
        job["status"] = "pending"
        job["error"] = None
        job["completed_at"] = None
        client.set(key, json.dumps(job), ex=JOB_TTL_SECONDS)


def get(job_id: str) -> dict | None:
    client = _client()
    data = client.get(f"{KEY_PREFIX}{job_id}")
    if data:
        return json.loads(data)
    return None


def list_by_user(user_id: str) -> list[dict]:
    client = _client()
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return []

    user_jobs_key = f"{USER_JOBS_PREFIX}{normalized_user_id}"
    job_ids = sorted(client.smembers(user_jobs_key))
    jobs: list[dict] = []
    for job_id in job_ids:
        data = client.get(f"{KEY_PREFIX}{job_id}")
        if data:
            jobs.append(json.loads(data))
    jobs.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return jobs


def get_cached_result_for_user_number(user_id: str, number: int) -> dict | None:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return None
    client = _client()
    data = client.get(f"{USER_NUM_PREFIX}{normalized_user_id}:{number}")
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
    client = _client()
    client.set(
        f"{USER_NUM_PREFIX}{normalized_user_id}:{number}",
        json.dumps(result),
        ex=JOB_TTL_SECONDS,
    )


def delete_number_cache_for_user(user_id: str) -> int:
    """Apaga o cache user_num:{uid}:* (dedupe por número). Retorna quantas chaves foram removidas."""
    client = _client()
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return 0
    pattern = f"{USER_NUM_PREFIX}{normalized_user_id}:*"
    keys = list(client.scan_iter(match=pattern, count=500))
    if not keys:
        return 0
    pipe = client.pipeline(transaction=False)
    for k in keys:
        pipe.delete(k)
    pipe.execute()
    return len(keys)


def delete_all_for_user(user_id: str) -> int:
    """Remove todas as chaves de jobs e o set user_jobs do utilizador. Retorna quantos jobs foram apagados."""
    client = _client()
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return 0
    user_jobs_key = f"{USER_JOBS_PREFIX}{normalized_user_id}"
    job_ids = list(client.smembers(user_jobs_key))
    if not job_ids:
        client.delete(user_jobs_key)
        return 0
    pipe = client.pipeline(transaction=False)
    for jid in job_ids:
        pipe.delete(f"{KEY_PREFIX}{jid}")
    pipe.delete(user_jobs_key)
    pipe.execute()
    return len(job_ids)
