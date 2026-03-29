from sqlalchemy import select
from sqlalchemy.orm import Session

from main_server.auth_core import hash_password
from main_server.models import User


def get_user_by_email(db: Session, email: str) -> User | None:
    normalized = email.strip().lower()
    return db.scalars(select(User).where(User.email == normalized)).first()


def create_user(db: Session, *, email: str, password: str) -> User:
    user = User(email=email.strip().lower(), hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
