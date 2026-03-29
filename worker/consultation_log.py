from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsultationRow:
    user_external_id: str
    number: int
    result: str
    job_id: str

DIGEST_DB_URL = os.environ.get("DIGEST_DB_URL", "sqlite:///./data/consultation_digest.db")


class Base(DeclarativeBase):
    pass


class ConsultationLog(Base):
    __tablename__ = "consultation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_external_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    # sempre UTC (naive) para compatível com SQLite
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)


_connect_args = {}
if DIGEST_DB_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    db_path = DIGEST_DB_URL.replace("sqlite:///", "", 1)
    if not db_path.startswith(":memory:"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DIGEST_DB_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
_tables_ready = False


def ensure_tables() -> None:
    global _tables_ready
    if not _tables_ready:
        Base.metadata.create_all(bind=engine)
        _tables_ready = True


@contextmanager
def session_scope() -> Iterator:
    ensure_tables()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def log_completed_consultation(
    *,
    user_external_id: str,
    number: int,
    result: str,
    job_id: str,
    completed_at_utc: datetime | None = None,
) -> None:
    when = completed_at_utc or datetime.now(timezone.utc)
    when_naive = when.replace(tzinfo=None)
    uid = user_external_id.strip()
    if not uid:
        return
    try:
        with session_scope() as db:
            row = ConsultationLog(
                user_external_id=uid,
                number=number,
                result=result,
                job_id=job_id,
                completed_at=when_naive,
            )
            db.add(row)
    except Exception:
        logger.warning("Não foi possível gravar consulta no digest DB (job %s)", job_id, exc_info=True)


def yesterday_window_utc(digest_tz_name: str) -> tuple[datetime, datetime, date]:
    """Intervalo [start, end) em UTC naive correspondente ao 'dia anterior' no fuso informado."""
    tz = ZoneInfo(digest_tz_name)
    now_local = datetime.now(tz)
    y_date = now_local.date() - timedelta(days=1)
    start_local = datetime(y_date.year, y_date.month, y_date.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc, y_date


def fetch_consultations_grouped_for_yesterday(
    digest_tz_name: str,
) -> tuple[dict[str, list[ConsultationRow]], date]:
    start_utc, end_utc, y_date = yesterday_window_utc(digest_tz_name)
    ensure_tables()
    with session_scope() as db:
        rows = db.scalars(
            select(ConsultationLog)
            .where(ConsultationLog.completed_at >= start_utc, ConsultationLog.completed_at < end_utc)
            .order_by(ConsultationLog.user_external_id, ConsultationLog.completed_at)
        ).all()
        snapshot = [
            ConsultationRow(
                user_external_id=r.user_external_id,
                number=r.number,
                result=r.result,
                job_id=r.job_id,
            )
            for r in rows
        ]

    by_user: dict[str, list[ConsultationRow]] = defaultdict(list)
    for r in snapshot:
        by_user[r.user_external_id].append(r)
    return dict(by_user), y_date


def delete_all_consultations_for_user(user_external_id: str) -> int:
    """Apaga linhas do digest SQLite para este utilizador (mesmo id que no Redis)."""
    uid = user_external_id.strip()
    if not uid:
        return 0
    ensure_tables()
    try:
        with session_scope() as db:
            result = db.execute(delete(ConsultationLog).where(ConsultationLog.user_external_id == uid))
            return int(result.rowcount or 0)
    except Exception:
        logger.warning("Falha ao limpar digest para o utilizador %s", uid, exc_info=True)
        return 0
