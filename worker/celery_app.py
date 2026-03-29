import os
from pathlib import Path

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

# Garante .env na raiz do projeto antes de ler REDIS_URL / tarefas (credenciais SMTP, etc.)
_root = Path(__file__).resolve().parents[1]
_env = _root / ".env"
if _env.is_file():
    load_dotenv(_env)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DIGEST_TZ = os.environ.get("DIGEST_TZ", "America/Sao_Paulo")

celery_app = Celery(
    "worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker.tasks", "worker.digest_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # 10:00 no fuso DIGEST_TZ (desliga UTC explícito para o crontab seguir o relógio local configurado)
    timezone=DIGEST_TZ,
    enable_utc=False,
    beat_schedule={
        "daily-consultation-digest-10am": {
            "task": "worker.digest_tasks.send_yesterday_digest",
            "schedule": crontab(hour=10, minute=0),
        },
    },
)
