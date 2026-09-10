"""Shared fixtures. Loads the sample dataset once for the whole test session."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.auth.context import AuthContext, Role, build_auth_context
from app.config import REPO_ROOT
from app.db.session import SessionLocal, engine
from app.models import User
from app.seed.load_csv import LOAD_ORDER, load

SAMPLE_DIR = REPO_ROOT / "data" / "synthetic" / "sample"


@pytest.fixture(scope="session", autouse=True)
def _loaded_db() -> None:
    """Ensure a freshly loaded sample DB before any test runs."""
    load("sample", reset=True)
    with engine.begin() as c:
        c.execute(text("TRUNCATE audit_log RESTART IDENTITY"))


def make_ctx(role: str, subject_id: int | None = None) -> AuthContext:
    """Build an AuthContext straight from the DB (bypasses HTTP)."""
    with SessionLocal() as db:
        q = select(User).where(User.role == role)
        if subject_id is not None:
            q = q.where(User.subject_ref == f"{role}:{subject_id}")
        user = db.scalars(q.limit(1)).one()
        return build_auth_context(
            {"sub": str(user.id), "subject_ref": user.subject_ref, "role": role}, db
        )


@pytest.fixture(scope="session")
def conn():
    with engine.connect() as c:
        yield c


def csv_row_count(name: str) -> int:
    path = SAMPLE_DIR / f"{name}.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1  # minus header
