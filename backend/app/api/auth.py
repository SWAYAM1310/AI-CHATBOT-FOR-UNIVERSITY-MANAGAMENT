"""Login: email + password -> JWT. Every synthetic user's password is `uniassist`."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_db
from app.auth.security import verify_password
from app.auth.tokens import create_access_token
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    subject_ref: str


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
    token = create_access_token(user_id=user.id, subject_ref=user.subject_ref, role=user.role)
    return TokenOut(access_token=token, role=user.role, subject_ref=user.subject_ref)
