from __future__ import annotations

import json
from typing import Any

import httpx

MOCK_RESERVED_FAILURE_NUMBER = 404
MOCK_ERROR_CODE_RESERVED = "MOCK_RESERVED_FAILURE_NUMBER"


def _parse_http_error_body(response: httpx.Response | None) -> tuple[Any, str | None, str | None]:
    """
    Devolve (objeto_json_ou_none, error_code, message_amigável).
    Para FastAPI com detail=dict, extrai error_code e message.
    """
    if response is None:
        return None, None, None
    try:
        body: Any = response.json()
    except (json.JSONDecodeError, ValueError):
        text = (response.text or "").strip()
        return None, None, (text[:500] if text else None)

    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, dict):
            code = d.get("error_code")
            msg = d.get("message")
            if isinstance(code, str) and isinstance(msg, str):
                return body, code, msg
            return body, (str(code) if code is not None else None), (
                str(msg) if msg is not None else json.dumps(d, ensure_ascii=False)[:500]
            )
        if isinstance(d, str):
            return body, None, d[:500]
    return body, None, None


def describe_mock_failure(
    exc: BaseException,
    *,
    number: int,
    url: str,
) -> dict[str, Any]:
    """
    Campos para montar um registo DLQ legível (resumo curto + metadados estáveis).
    """
    technical_type = type(exc).__name__
    technical_message = str(exc)[:800]

    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        status = resp.status_code if resp is not None else None
        _body, api_error_code, api_message = _parse_http_error_body(resp)

        is_reserved = api_error_code == MOCK_ERROR_CODE_RESERVED or (
            number == MOCK_RESERVED_FAILURE_NUMBER and status == 422
        )

        if is_reserved:
            return {
                "error_category": "mock_reserved_test_number",
                "mock_error_code": MOCK_ERROR_CODE_RESERVED,
                "http_status": status,
                "mock_url": url,
                "operator_summary": (
                    f"{MOCK_ERROR_CODE_RESERVED}: numero 404 reservado no mock para testes de DLQ; "
                    f"HTTP {status}. Falha simulada no mock."
                ),
                "technical_exception": technical_type,
            }

        mock_preview: str | None
        if api_message:
            mock_preview = api_message
        elif isinstance(_body, dict):
            mock_preview = json.dumps(_body, ensure_ascii=False)[:400]
        else:
            mock_preview = (resp.text or "").strip()[:400] or None

        if status is not None and 400 <= status < 500:
            category = "mock_http_client_error"
        elif status is not None and status >= 500:
            category = "mock_http_server_error"
        else:
            category = "mock_http_error"

        return {
            "error_category": category,
            "mock_error_code": api_error_code,
            "http_status": status,
            "mock_url": url,
            "operator_summary": (
                f"O mock respondeu HTTP {status}"
                + (f" ({api_error_code})" if api_error_code else "")
                + f". {mock_preview or 'Sem detalhe no corpo.'}"
            )[:600],
            "technical_exception": technical_type,
        }

    if isinstance(exc, httpx.TimeoutException):
        return {
            "error_category": "mock_timeout",
            "mock_error_code": None,
            "http_status": None,
            "mock_url": url,
            "operator_summary": "Timeout ao contactar o mock. Verifique latência e disponibilidade do serviço.",
            "technical_exception": technical_type,
        }

    if isinstance(exc, httpx.ConnectError):
        return {
            "error_category": "mock_connection_failed",
            "mock_error_code": None,
            "http_status": None,
            "mock_url": url,
            "operator_summary": (
                "Falha de ligação ao mock (rede/DNS/MOCK_SERVER_URL). O serviço pode não estar acessível."
            ),
            "technical_exception": technical_type,
        }

    if isinstance(exc, json.JSONDecodeError):
        return {
            "error_category": "mock_invalid_json_response",
            "mock_error_code": None,
            "http_status": None,
            "mock_url": url,
            "operator_summary": "Resposta do mock não é JSON válido no formato esperado.",
            "technical_exception": technical_type,
        }

    if isinstance(exc, httpx.RequestError):
        return {
            "error_category": "mock_request_error",
            "mock_error_code": None,
            "http_status": None,
            "mock_url": url,
            "operator_summary": f"Erro de pedido HTTP ({technical_type}).",
            "technical_exception": technical_type,
        }

    return {
        "error_category": "unexpected_error",
        "mock_error_code": None,
        "http_status": None,
        "mock_url": url,
        "operator_summary": f"Falha não classificada: {technical_type}",
        "technical_exception": technical_type,
    }


def dlq_debug_technical_message(exc: BaseException) -> str:
    """Texto técnico curto opcional para o campo debug da DLQ."""
    return str(exc)[:500]
