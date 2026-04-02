import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/users.db")

_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    parsed = make_url(DATABASE_URL)
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _ensure_sqlite_column_users_is_superuser() -> None:
    """Bases SQLite antigas sem is_superuser: ADD COLUMN (create_all não altera tabelas existentes)."""
    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "is_superuser" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE users ADD COLUMN is_superuser INTEGER NOT NULL DEFAULT 0")
        )


def init_db() -> None:
    from main_server import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_column_users_is_superuser()
