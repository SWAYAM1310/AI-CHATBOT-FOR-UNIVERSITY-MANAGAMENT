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


@pytest.fixture(scope="session", autouse=True)
def _preserve_doc_store(_loaded_db) -> None:
    """Put the ingested corpus back the way it was after the session.

    The RAG tests truncate `documents` / `doc_chunks` and re-ingest with no or a
    fake embedder; without this, one `pytest` run leaves the dev database with
    NULL or fake vectors until the next `--force` ingest with a real key.
    """
    with engine.begin() as c:
        docs = c.execute(text("SELECT * FROM documents")).mappings().all()
        chunks = c.execute(text("SELECT * FROM doc_chunks")).mappings().all()
        links = c.execute(text("SELECT id, source_chunk_id FROM academic_calendar WHERE source_chunk_id IS NOT NULL")).mappings().all()
    yield
    with engine.begin() as c:
        c.execute(text("UPDATE academic_calendar SET source_chunk_id = NULL"))
        c.execute(text("TRUNCATE doc_chunks, documents RESTART IDENTITY CASCADE"))
        if docs:
            c.execute(text(_insert_sql("documents", docs[0].keys())), [dict(r) for r in docs])
        if chunks:
            rows = [{**r, "embedding": str(r["embedding"]) if r["embedding"] is not None else None} for r in chunks]
            c.execute(text(_insert_sql("doc_chunks", chunks[0].keys())), rows)
        for t in ("documents", "doc_chunks"):
            c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE(MAX(id), 1)) FROM {t}"))
        for r in links:
            c.execute(text("UPDATE academic_calendar SET source_chunk_id = :cid WHERE id = :id"), dict(r))


def _insert_sql(table: str, columns) -> str:
    cols = list(columns)
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"


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
