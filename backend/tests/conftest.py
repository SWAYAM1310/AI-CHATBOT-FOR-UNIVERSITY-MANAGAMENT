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
DOC_STORE_EXTRACT_TABLES = ("syllabus_courses", "syllabus_units", "course_outcomes", "textbooks")


@pytest.fixture(scope="session", autouse=True)
def _loaded_db(_preserve_doc_store) -> None:
    """Ensure a freshly loaded sample DB before any test runs."""
    load("sample", reset=True)
    with engine.begin() as c:
        c.execute(text("TRUNCATE audit_log RESTART IDENTITY"))


@pytest.fixture(scope="session", autouse=True)
def _preserve_doc_store() -> None:
    """Put the ingested corpus back the way it was after the session.

    The RAG tests truncate `documents` / `doc_chunks` and re-ingest with no or a
    fake embedder; without this, one `pytest` run leaves the dev database with
    NULL or fake vectors until the next `--force` ingest with a real key. The
    snapshot is taken before the sample reload: its `TRUNCATE ... CASCADE` of
    `subjects` would otherwise already have emptied `syllabus_courses`.
    """
    with engine.begin() as c:
        docs = c.execute(text("SELECT * FROM documents")).mappings().all()
        chunks = c.execute(text("SELECT * FROM doc_chunks")).mappings().all()
        extract = {t: c.execute(text(f"SELECT * FROM {t}")).mappings().all() for t in DOC_STORE_EXTRACT_TABLES}
        cal_links = c.execute(text("SELECT id, source_chunk_id FROM academic_calendar WHERE source_chunk_id IS NOT NULL")).mappings().all()
    yield
    with engine.begin() as c:
        c.execute(text("UPDATE academic_calendar SET source_chunk_id = NULL"))
        c.execute(text("TRUNCATE doc_chunks, documents RESTART IDENTITY CASCADE"))  # cascades to the extract tables
        if docs:
            c.execute(text(_insert_sql("documents", docs[0].keys())), [dict(r) for r in docs])
        if chunks:
            # parents first (NULL links), then the self-FK links, so row order cannot matter
            rows = [{**r, "parent_chunk_id": None} for r in chunks]
            c.execute(text(_insert_sql("doc_chunks", chunks[0].keys())), rows)
            links = [{"id": r["id"], "parent": r["parent_chunk_id"]} for r in chunks if r["parent_chunk_id"] is not None]
            if links:
                c.execute(text("UPDATE doc_chunks SET parent_chunk_id = :parent WHERE id = :id"), links)
        for t in DOC_STORE_EXTRACT_TABLES:  # parents (courses) before children
            if extract[t]:
                c.execute(text(_insert_sql(t, extract[t][0].keys())), [dict(r) for r in extract[t]])
        for t in ("documents", "doc_chunks", *DOC_STORE_EXTRACT_TABLES):
            c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE(MAX(id), 1)) FROM {t}"))
        for r in cal_links:
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
