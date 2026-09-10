"""JWT encode/decode. The token carries only identity — role and scoping are
re-derived server-side into an AuthContext, never trusted from the client.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings


def create_access_token(*, user_id: int, subject_ref: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "subject_ref": subject_ref,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on any problem (expired, tampered, wrong alg)."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
