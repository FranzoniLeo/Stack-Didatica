from __future__ import annotations

import json
import os
import time

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DLQ_LIST_KEY = os.environ.get("DLQ_REDIS_KEY", "dlq:process_even_odd")
DLQ_MAX_ENTRIES = int(os.environ.get("DLQ_MAX_ENTRIES", "2000"))
_ERROR_MAX_LEN = 2000


def record_dead_letter(
    *,
    job_id: str,
    number: int,
    user_id: str | None,
    attempts: int,
    error_message: str,
) -> None:
    payload = {
        "task": "process_even_odd",
        "job_id": job_id,
        "number": number,
        "user_id": user_id,
        "attempts": attempts,
        "failed_at": time.time(),
        "error": (error_message or "")[:_ERROR_MAX_LEN],
    }
    client = redis.from_url(REDIS_URL, decode_responses=True)
    client.rpush(DLQ_LIST_KEY, json.dumps(payload, ensure_ascii=False))
    if DLQ_MAX_ENTRIES > 0:
        client.ltrim(DLQ_LIST_KEY, -DLQ_MAX_ENTRIES, -1)
