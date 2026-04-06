from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from main_server.auth_core import (
    ACCESS_TOKEN_COOKIE,
    access_token_cookie_max_age_seconds,
    access_token_cookie_secure,
    create_access_token,
    get_current_user,
    get_db,
    verify_password,
)
from main_server.crud_users import create_user, get_user_by_email
from main_server.models import User
from main_server.schemas import LoginBody, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, str(body.email)):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = create_user(db, email=str(body.email), password=body.password)
    return user


@router.post("/login", response_model=UserOut)
def login(response: Response, body: LoginBody, db: Session = Depends(get_db)):
    user = get_user_by_email(db, str(body.email))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")
    token = create_access_token(subject=str(user.id))
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=access_token_cookie_max_age_seconds(),
        httponly=True,
        samesite="lax",
        secure=access_token_cookie_secure(),
        path="/",
    )
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=ACCESS_TOKEN_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user
