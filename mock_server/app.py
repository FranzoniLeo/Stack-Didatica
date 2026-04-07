"""
Servidor simulado: recebe um número, dorme 30 segundos, responde se é par ou ímpar.

O número 404 devolve 422 + JSON estruturado (falha de negócio simulada), para testes de DLQ/reprocessamento.

Uso: uvicorn mock_server.app:app --host 127.0.0.1 --port 8001
"""
import asyncio

from fastapi import FastAPI, HTTPException, status

SLEEP_SECONDS = 30

# Código estável para a DLQ / reprocessadores — não é HTTP 404 de rota em falta.
MOCK_ERROR_RESERVED_NUMBER = "MOCK_RESERVED_FAILURE_NUMBER"

app = FastAPI(title="Servidor Mock - Par/Ímpar")


@app.get("/even-odd/{number}")
async def even_odd(number: int):
    """Dorme 30 segundos e retorna se o número é par ou ímpar."""
    if number == 404:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": MOCK_ERROR_RESERVED_NUMBER,
                "message": (
                    "Numero 404 reservado para testes: o mock recusa este valor por regra simulada "
                    "(falha de negocio de teste, sem confundir com pagina nao encontrada)."
                ),
                "number": 404,
                "endpoint": "GET /even-odd/{number}",
            },
        )
    await asyncio.sleep(SLEEP_SECONDS)
    result = "par" if number % 2 == 0 else "ímpar"
    return {"number": number, "result": result}
