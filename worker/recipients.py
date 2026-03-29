"""
Resolve o e-mail para o digest diário.

`user_external_id` é o mesmo valor guardado no Redis (id numérico do usuário em string).

Se `USERS_DB_PATH` apontar para o SQLite do main_server (`users.db`), o e-mail é lido da tabela `users`.
Sem essa variável, o digest não envia e-mail (comportamento anterior).
"""
from __future__ import annotations

import os
import sqlite3


def get_digest_email(user_external_id: str) -> str | None:
    path = os.environ.get("USERS_DB_PATH", "").strip()
    if not path:
        return None
    try:
        uid = int(user_external_id)
    except ValueError:
        return None
    try:
        conn = sqlite3.connect(path)
        try:
            row = conn.execute(
                "SELECT email FROM users WHERE id = ?",
                (uid,),
            ).fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return None
    return row[0] if row else None
