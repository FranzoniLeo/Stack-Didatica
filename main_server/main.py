from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from main_server.database import init_db
from main_server.routes.admin_dlq_routes import router as admin_dlq_router
from main_server.routes.auth_routes import router as auth_router
from main_server.routes.job_routes import router as job_router

app = FastAPI()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.include_router(auth_router)
app.include_router(job_router)
app.include_router(admin_dlq_router)


@app.on_event("startup")
def startup():
    init_db()
    print("[main_server] SQLite + usuários (e-mail/senha) + Celery")


@app.get("/api/mode")
def api_mode():
    return {"mode": "assíncrono", "worker": "celery", "auth": "jwt"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"mode": "assíncrono"},
    )
