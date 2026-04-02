from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import redis

from worker.mock_client_errors import describe_mock_failure, dlq_debug_technical_message

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DLQ_LIST_KEY = os.environ.get("DLQ_REDIS_KEY", "dlq:process_even_odd")
DLQ_MAX_ENTRIES = int(os.environ.get("DLQ_MAX_ENTRIES", "2000"))


def record_dead_letter(
    *,
    job_id: str,
    number: int,
    user_id: str | None,
    attempts: int,
    mock_url: str,
    exception: BaseException,
) -> None:
    ctx: dict[str, Any] = describe_mock_failure(exception, number=number, url=mock_url)
    # Payload enxuto: "summary" é o que operadores / scripts devem ler primeiro.
    payload: dict[str, Any] = {
        "dlq_entry_id": uuid.uuid4().hex,
        "task": "process_even_odd",
        "job_id": job_id,
        "number": number,
        "user_id": user_id,
        "attempts": attempts,
        "failed_at": time.time(),
        "summary": ctx["operator_summary"],
        "error_category": ctx["error_category"],
        "mock_error_code": ctx.get("mock_error_code"),
        "http_status": ctx.get("http_status"),
        "mock_url": ctx.get("mock_url"),
        "debug": {
            "exception_type": ctx.get("technical_exception"),
            "httpx_message": dlq_debug_technical_message(exception),
        },
    }
    client = redis.from_url(REDIS_URL, decode_responses=True)
    client.rpush(DLQ_LIST_KEY, json.dumps(payload, ensure_ascii=True))
    if DLQ_MAX_ENTRIES > 0:
        client.ltrim(DLQ_LIST_KEY, -DLQ_MAX_ENTRIES, -1)


def _redis_decode() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def list_dlq_entries() -> list[dict[str, Any]]:
    """Todas as entradas da DLQ (ordem: mais antiga primeiro)."""
    client = _redis_decode()
    items = client.lrange(DLQ_LIST_KEY, 0, -1)
    out: list[dict[str, Any]] = []
    for raw in items:
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            out.append({"dlq_parse_error": True, "raw_preview": (raw or "")[:240]})
    return out


def peek_dlq_entry(
    *,
    dlq_entry_id: str | None = None,
    legacy_job_id: str | None = None,
) -> tuple[dict[str, Any], str] | None:
    """
    Localiza entrada sem remover. Devolve (payload, linha_raw) para LREM exacto.
    Se dlq_entry_id for passado, ignora legacy_job_id.
    """
    if not dlq_entry_id and not legacy_job_id:
        return None
    client = _redis_decode()
    want_job = None if dlq_entry_id else legacy_job_id
    eid = dlq_entry_id.strip() if dlq_entry_id else None
    jid = want_job.strip() if want_job else None
    for raw in client.lrange(DLQ_LIST_KEY, 0, -1):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if eid and data.get("dlq_entry_id") == eid:
            return data, raw
        if jid and data.get("job_id") == jid:
            return data, raw
    return None


def remove_dlq_raw_line(raw_line: str) -> int:
    """Remove uma linha exacta da lista. Retorno: número de elementos removidos."""
    return int(_redis_decode().lrem(DLQ_LIST_KEY, 1, raw_line))


def reappend_dlq_raw(raw_line: str) -> None:
    """Recoloca uma entrada no fim da DLQ (após falha ao reprocessar)."""
    _redis_decode().rpush(DLQ_LIST_KEY, raw_line)
