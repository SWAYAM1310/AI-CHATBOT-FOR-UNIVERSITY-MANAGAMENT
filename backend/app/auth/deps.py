"""FastAPI auth dependencies."""
from __future__ import annotations

from collections.abc import Iterator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.context import AuthContext, AuthError, Role, build_auth_context
from app.auth.tokens import decode_access_token
from app.db.session import SessionLocal

_bearer = HTTPBearer(auto_error=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_auth_context(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc
    try:
        return build_auth_context(payload, db)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


def require_roles(*roles: Role):
    allowed = set(roles)

    def _dep(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return ctx

    return _dep
