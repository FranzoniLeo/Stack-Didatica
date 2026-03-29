"""
Servidor simulado: recebe um número, dorme 30 segundos, responde se é par ou ímpar.

Uso: uvicorn mock_server.app:app --host 127.0.0.1 --port 8001
"""
import asyncio
from fastapi import FastAPI

SLEEP_SECONDS = 30

app = FastAPI(title="Servidor Mock - Par/Ímpar")


@app.get("/even-odd/{number}")
async def even_odd(number: int):
    """Dorme 30 segundos e retorna se o número é par ou ímpar."""
    await asyncio.sleep(SLEEP_SECONDS)
    result = "par" if number % 2 == 0 else "ímpar"
    return {"number": number, "result": result}
