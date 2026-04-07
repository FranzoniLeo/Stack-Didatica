import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from main_server.database import SessionLocal
from main_server.models import User

# bcrypt limita a senha a 72 bytes (UTF-8)
def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]

SECRET_KEY = os.environ.get("SECRET_KEY", "troque-em-producao-use-uma-chave-longa")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))

# Cookie HttpOnly (browser): o JS não lê; enviado automaticamente com credentials: 'include'.
ACCESS_TOKEN_COOKIE = "access_token"
security = HTTPBearer(auto_error=False)


def access_token_cookie_max_age_seconds() -> int:
    return ACCESS_TOKEN_EXPIRE_MINUTES * 60


def access_token_cookie_secure() -> bool:
    """Em produção com HTTPS, defina COOKIE_SECURE=true."""
    return os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true", "yes")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    """Hash com bcrypt (sem passlib — evita conflito bcrypt 4.1+ / passlib 1.7.4)."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(plain), hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(*, subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": subject, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token and credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        user_id = int(sub)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Rotas de administração: apenas utilizadores com `is_superuser` (ver `scripts/create_superuser.py`)."""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: necessário superuser.",
        )
    return user
