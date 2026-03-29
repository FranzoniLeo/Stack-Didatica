# Stack-Didatica: notificações e jobs assíncronos

Aplicação didática que simula consultas a um servidor com **processamento em background**: API **REST** (FastAPI), **login e JWT**, fila e estado em **Redis**, worker **Celery**, **agendamento** com **Beat** (digest por e-mail), **cache de resultados** e **deduplicação** por utilizador+número, **reprocessamento** em falhas transitórias. Tudo orquestrado com **Docker Compose**. Utilizadores e histórico para digest usam **SQLite** e **Redis** (filas, jobs, cache).

---

## Rodar o Docker

```bash
docker compose up --build
```

**URL:** http://localhost:8000

Para ver os registros da DLQ no Redis:
```bash
docker compose exec redis redis-cli LRANGE dlq:process_even_odd 0 -1
```

Para disparar o digest manualmente:

`celery -A worker.celery_app call worker.digest_tasks.send_yesterday_digest`

Sem Docker, além do worker rode em outro terminal:

`celery -A worker.celery_app beat --loglevel=info`.

### Sem Docker

**1. Redis** (se não estiver rodando)

```bash
docker run -d -p 6379:6379 redis:alpine
```

**2. Mock server** (porta 8001)

```bash
source venv/bin/activate
uvicorn mock_server.app:app --host 127.0.0.1 --port 8001
```

**3. Main server** (porta 8000)

```bash
source venv/bin/activate
uvicorn main_server.main:app --host 127.0.0.1 --port 8000
```

**4. Worker Celery**

```bash
source venv/bin/activate
celery -A worker.celery_app worker --loglevel=info
```

**5. Celery Beat** (agendamento do digest 10h — opcional se não for usar e-mail)

```bash
source venv/bin/activate
celery -A worker.celery_app beat --loglevel=info
```
