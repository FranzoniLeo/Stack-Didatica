#!/usr/bin/env python3
"""
Criar ou promover superutilizador (equivalente prático ao Django createsuperuser).

Uso na raiz do projeto, com o venv ativo:

    python scripts/create_superuser.py

Carrega `.env` na raiz, se existir.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.is_file():
    from dotenv import load_dotenv

    load_dotenv(_env)

from main_server.auth_core import hash_password
from main_server.crud_users import get_user_by_email
from main_server.database import DATABASE_URL, SessionLocal, init_db
from main_server.models import User


def main() -> None:
    init_db()
    email = input("E-mail: ").strip().lower()
    if not email:
        print("E-mail obrigatório.", file=sys.stderr)
        sys.exit(1)
    pw = getpass.getpass("Senha: ")
    pw2 = getpass.getpass("Senha (novamente): ")
    if pw != pw2:
        print("As senhas não coincidem.", file=sys.stderr)
        sys.exit(1)
    if len(pw) < 8:
        print("Mínimo 8 caracteres.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = get_user_by_email(db, email)
        if existing:
            existing.hashed_password = hash_password(pw)
            existing.is_superuser = True
            db.commit()
            print(f"OK — utilizador existente promovido a superuser: {email}")
        else:
            u = User(email=email, hashed_password=hash_password(pw), is_superuser=True)
            db.add(u)
            db.commit()
            print(f"OK — superuser criado: {email}")
        print(f"(SQLite usado: {DATABASE_URL})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
