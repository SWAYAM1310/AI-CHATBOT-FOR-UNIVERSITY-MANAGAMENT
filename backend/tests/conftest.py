"""Shared fixtures. Loads the sample dataset once for the whole test session."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.auth.context import AuthContext, Role, build_auth_context
from app.config import REPO_ROOT, settings
from app.db.session import SessionLocal, engine
from app.jobs.upkeep import LOCK_KEY, run_now
from app.models import User
from app.seed.load_csv import LOAD_ORDER, load

# Tests expect the CSV's raw state (classes still "due", marks still missing), so the
# upkeep job stays off: in this process, and in any dev server sharing the database,
# which finds its lock taken (see _upkeep_locked_out).
settings.upkeep_enabled = False

SAMPLE_DIR = REPO_ROOT / "data" / "synthetic" / "sample"
DOC_STORE_EXTRACT_TABLES = ("syllabus_courses", "syllabus_units", "course_outcomes", "textbooks")


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch) -> None:
    """No test may reach a real mail server, whatever backend/.env says.

    A developer's .env can point at Gmail with a redirect to their own inbox; the
    confirm endpoints send after commit, so a test that confirms an action would
    otherwise email a real person on every run. Tests that exercise the redirect,
    the demo cap or a transport set what they need themselves, on top of this.
    """
    monkeypatch.setattr(settings, "email_mode", "console")
    monkeypatch.setattr(settings, "email_redirect_to", "")
    monkeypatch.setattr(settings, "smtp_host", "localhost")


@pytest.fixture(scope="session", autouse=True)
def _upkeep_locked_out():
    """Hold the upkeep job's lock for the whole session, so a running dev server cannot
    fill in attendance or marks while the tests count rows. The session reloads the dev
    database from CSV, so afterwards the job settles it again rather than leaving it
    raw until the server's next run."""
    with engine.connect() as c:
        c.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
        c.commit()
        yield
        c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
        c.commit()
    run_now()


@pytest.fixture(scope="session", autouse=True)
def _loaded_db(_preserve_doc_store, _upkeep_locked_out) -> None:
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
        calendar = c.execute(text("SELECT * FROM academic_calendar ORDER BY id")).mappings().all()
    yield
    with engine.begin() as c:
        # the calendar is CSV-loaded but the tabular ingest links (and tests mutate) its rows: restore it whole
        c.execute(text("TRUNCATE academic_calendar RESTART IDENTITY"))
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
        if calendar:
            c.execute(text(_insert_sql("academic_calendar", calendar[0].keys())), [dict(r) for r in calendar])
        for t in ("documents", "doc_chunks", "academic_calendar", *DOC_STORE_EXTRACT_TABLES):
            c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE(MAX(id), 1)) FROM {t}"))


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
