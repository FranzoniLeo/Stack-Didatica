# Stack-Didatica: notificações e jobs assíncronos

Aplicação didática que simula consultas a um servidor com **processamento em background**: API **REST** (FastAPI), **login e JWT**, fila e broker **Redis**, worker **Celery**, **agendamento** com **Beat** (digest por e-mail), **cache de resultados** e **deduplicação** por utilizador+número, **reprocessamento** em falhas transitórias. Os **jobs** (estado e histórico) persistem em **MongoDB**; **Redis** mantém idempotência (`idemp`), cache por número (`user_num`), filas Celery e DLQ. Utilizadores e digest usam **SQLite**.

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

Defina `MONGODB_URL` (ex.: `mongodb://127.0.0.1:27017`) e `MONGODB_DB` (opcional, default `email_notification`) para **main** e **worker**.

**1. Redis** (se não estiver rodando)

```bash
docker run -d -p 6379:6379 redis:alpine
```

**2. MongoDB** (porta 27017)

```bash
docker run -d -p 27017:27017 mongo:7
```

**3. Mock server** (porta 8001)

```bash
source venv/bin/activate
uvicorn mock_server.app:app --host 127.0.0.1 --port 8001
```

**4. Main server** (porta 8000)

```bash
source venv/bin/activate
uvicorn main_server.main:app --host 127.0.0.1 --port 8000
```

**5. Worker Celery**

```bash
source venv/bin/activate
celery -A worker.celery_app worker --loglevel=info
```

**6. Celery Beat** (agendamento do digest 10h — opcional se não for usar e-mail)

```bash
source venv/bin/activate
celery -A worker.celery_app beat --loglevel=info
```
