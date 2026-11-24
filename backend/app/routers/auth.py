"""Sign in and find out who is signed in."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User
from ..services.auth import authenticate, create_token, current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=1, max_length=200)


def _user_out(u: User) -> dict:
    return {"username": u.username, "full_name": u.full_name, "role": u.role}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = authenticate(db, body.username, body.password)
    return {"access_token": create_token(user), "token_type": "bearer",
            "expires_in_minutes": settings.auth_token_minutes, "user": _user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user_out(user)
