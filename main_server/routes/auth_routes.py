from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from main_server.auth_core import create_access_token, get_current_user, get_db, verify_password
from main_server.crud_users import create_user, get_user_by_email
from main_server.models import User
from main_server.schemas import LoginBody, Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, str(body.email)):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    user = create_user(db, email=str(body.email), password=body.password)
    return user


@router.post("/login", response_model=Token)
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = get_user_by_email(db, str(body.email))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")
    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user
