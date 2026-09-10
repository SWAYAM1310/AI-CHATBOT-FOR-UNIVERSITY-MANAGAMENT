"""Login + JWT + AuthContext wiring."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.tokens import decode_access_token
from app.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import User

client = TestClient(app)
DEV_PW = "uniassist"


def _one_email(role: str) -> str:
    with SessionLocal() as db:
        return db.scalars(select(User.email).where(User.role == role).limit(1)).one()


@pytest.mark.parametrize("role", ["student", "faculty", "admin"])
def test_login_ok_for_each_role(role):
    r = client.post("/api/auth/login", json={"email": _one_email(role), "password": DEV_PW})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == role
    payload = decode_access_token(body["access_token"])
    assert payload["role"] == role and payload["subject_ref"].startswith(role + ":")


def test_login_bad_password():
    r = client.post("/api/auth/login", json={"email": _one_email("student"), "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_email():
    r = client.post("/api/auth/login", json={"email": "nobody@nowhere.test", "password": DEV_PW})
    assert r.status_code == 401


def test_me_requires_token():
    assert client.get("/api/me").status_code in (401, 403)


def test_me_returns_scoped_profile():
    email = _one_email("student")
    tok = client.post("/api/auth/login", json={"email": email, "password": DEV_PW}).json()["access_token"]
    r = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "student"
    assert body["profile"]["role"] == "student"
    assert body["term"] == settings.current_term


def test_tampered_token_rejected():
    email = _one_email("faculty")
    tok = client.post("/api/auth/login", json={"email": email, "password": DEV_PW}).json()["access_token"]
    bad = tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb")
    r = client.get("/api/me", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_expired_token_rejected():
    email = _one_email("student")
    with SessionLocal() as db:
        u = db.scalars(select(User).where(User.email == email)).one()
    expired = jwt.encode(
        {"sub": str(u.id), "subject_ref": u.subject_ref, "role": u.role, "exp": 1_000_000_000},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    r = client.get("/api/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
