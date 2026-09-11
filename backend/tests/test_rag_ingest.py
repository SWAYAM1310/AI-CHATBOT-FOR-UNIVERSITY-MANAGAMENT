"""Phase 3 steps 1 & 3 — manifest, parsers, ingest, full-text policy search.

Runs against the 7 synthetic policy PDFs in docs/policies/pdf (a few seconds).
The curriculum PDFs are excluded here: 500 pages of parsing is for the CLI.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.ai.rag import ingest as ingest_mod
from app.ai.rag.ingest import ChunkDraft, ingest, ingest_one, page_chunks
from app.ai.rag.manifest import DEFAULT_MANIFEST, ManifestEntry, ManifestError, load_manifest
from app.ai.rag.parsers import extract_tables, normalize, parse_pdf
from app.ai.tools.registry import REGISTRY
from app.config import REPO_ROOT
from app.db.session import SessionLocal
from app.models import DocChunk, Document
from tests.conftest import make_ctx

ATTENDANCE_PDF = REPO_ROOT / "docs" / "policies" / "pdf" / "attendance_regulations.pdf"
EXAM_PDF = REPO_ROOT / "docs" / "policies" / "pdf" / "examination_regulations.pdf"
ATTENDANCE_CHUNKS = 40  # preamble + 39 top-level clauses (sub-clauses fold into their parent)


@pytest.fixture(scope="module")
def policies() -> list[ManifestEntry]:
    return [e for e in load_manifest() if e.doc_type == "policy"]


@pytest.fixture(scope="module", autouse=True)
def _ingested(policies):
    """A clean, complete policy ingest for this module (documents survive the CSV reset)."""
    with SessionLocal() as db:
        db.execute(text("UPDATE academic_calendar SET source_chunk_id = NULL"))
        db.execute(text("TRUNCATE doc_chunks, documents RESTART IDENTITY CASCADE"))
        db.commit()
    report = ingest(policies)
    assert not report.failed, report.failed
    assert len(report.ingested) == 7


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


# --- manifest -------------------------------------------------------------------

def test_manifest_loads_every_declared_file():
    entries = load_manifest(DEFAULT_MANIFEST)
    assert len(entries) == 13
    assert {e.doc_type for e in entries} == {"policy", "curriculum"}
    assert all(e.path.is_file() for e in entries)
    assert all(not e.source_path.startswith("/") and "\\" not in e.source_path for e in entries)
    att = next(e for e in entries if e.path == ATTENDANCE_PDF)
    assert (att.category, att.effective_date) == ("attendance", date(2026, 6, 16))
    assert att.audience_roles == ("student", "faculty", "admin")


@pytest.mark.parametrize(
    "body,needle",
    [
        ("documents: []", "no `documents`"),
        ("documents:\n  - title: x\n    doc_type: policy\n    audience_roles: [student]", "missing `path`"),
        ("documents:\n  - path: docs/manifest.yaml\n    title: x\n    doc_type: memo\n    audience_roles: [student]", "doc_type"),
        ("documents:\n  - path: docs/manifest.yaml\n    title: x\n    doc_type: policy\n    audience_roles: [root]", "audience_roles"),
        ("documents:\n  - path: docs/nope.pdf\n    title: x\n    doc_type: policy\n    audience_roles: [student]", "not found"),
        (
            "documents:\n  - path: docs/manifest.yaml\n    title: x\n    doc_type: policy\n    audience_roles: [student]\n"
            "  - path: docs/manifest.yaml\n    title: y\n    doc_type: policy\n    audience_roles: [student]",
            "duplicate",
        ),
    ],
)
def test_manifest_rejects_bad_entries(tmp_path: Path, body, needle):
    m = tmp_path / "m.yaml"
    m.write_text(body, encoding="utf-8")
    with pytest.raises(ManifestError, match=needle):
        load_manifest(m)


# --- parsers --------------------------------------------------------------------

def test_normalize_folds_ligatures_and_whitespace():
    assert normalize("eﬃcient    text \n\n\n\n next") == "eﬃcient text".replace("ﬃ", "ffi") + "\n\nnext"


def test_parse_pdf_keeps_page_numbers_honest():
    parsed = parse_pdf(ATTENDANCE_PDF)
    assert parsed.page_count == 4
    assert [p.number for p in parsed.pages] == [1, 2, 3, 4]
    assert "seventy-five" in parsed.pages[1].text  # §4.2 is on page 2
    assert "ﬃ" not in parsed.text and "ﬁ" not in parsed.text


def test_tables_come_out_as_rows():
    tables = extract_tables(EXAM_PDF, pages=[1, 2])
    flat = [cell for t in tables for row in t.rows for cell in row]
    assert "Quiz-1" in flat and "End-Sem" in flat


# --- ingest ---------------------------------------------------------------------

def test_documents_and_clause_chunks_are_written(db, policies):
    docs = db.scalars(select(Document).order_by(Document.id)).all()
    assert {d.source_path for d in docs} == {e.source_path for e in policies}
    for d in docs:
        assert d.doc_type == "policy" and d.version and len(d.version) == 64
        assert d.audience_roles == ["student", "faculty", "admin"]
    att = next(d for d in docs if d.source_path.endswith("attendance_regulations.pdf"))
    chunks = db.scalars(select(DocChunk).where(DocChunk.document_id == att.id).order_by(DocChunk.id)).all()
    assert len(chunks) == ATTENDANCE_CHUNKS
    assert sorted({c.page for c in chunks}) == [1, 2, 3, 4]
    assert all(c.embedding is None and c.tsv is not None for c in chunks)


def test_page_chunks_is_the_fallback_for_unregistered_types(policies, monkeypatch):
    att = next(e for e in policies if e.path == ATTENDANCE_PDF)
    monkeypatch.delitem(ingest_mod.CHUNKERS, "policy")
    assert [c.page for c in ingest_mod.CHUNKERS.get("policy", page_chunks)(parse_pdf(att.path), att)] == [1, 2, 3, 4]


def test_reingest_is_a_noop_unless_forced_or_changed(db, policies):
    att = next(e for e in policies if e.path == ATTENDANCE_PDF)
    before = db.scalar(select(func.max(DocChunk.id)))
    assert ingest_one(att, db) is None  # unchanged
    assert ingest_one(att, db, force=True) == ATTENDANCE_CHUNKS  # rewritten
    assert db.scalar(select(func.max(DocChunk.id))) > before
    assert db.scalar(select(func.count(Document.id)).where(Document.source_path == att.source_path)) == 1


def test_a_changed_file_is_rechunked_and_its_metadata_refreshed(db, policies, monkeypatch):
    att = next(e for e in policies if e.path == ATTENDANCE_PDF)
    monkeypatch.setattr(ingest_mod, "file_digest", lambda _p: "0" * 64)
    retitled = ManifestEntry(**{**att.__dict__, "title": "Renamed"})
    assert ingest_one(retitled, db) == ATTENDANCE_CHUNKS
    doc = db.scalars(select(Document).where(Document.source_path == att.source_path)).one()
    assert (doc.title, doc.version) == ("Renamed", "0" * 64)
    monkeypatch.undo()
    ingest_one(att, db)  # restore for the other tests


def test_a_failing_file_does_not_stop_the_run(policies, monkeypatch):
    def boom(parsed, entry):
        if entry.path == ATTENDANCE_PDF:
            raise RuntimeError("bad pdf")
        return page_chunks(parsed, entry)

    monkeypatch.setitem(ingest_mod.CHUNKERS, "policy", boom)
    report = ingest(policies, force=True)
    assert list(report.failed) == [next(e.source_path for e in policies if e.path == ATTENDANCE_PDF)]
    assert "bad pdf" in next(iter(report.failed.values()))
    assert len(report.ingested) == 6
    monkeypatch.undo()
    assert ingest(policies, force=True).failed == {}


def test_parent_links_resolve_by_draft_index(db, policies):
    att = next(e for e in policies if e.path == ATTENDANCE_PDF)
    monkeypatch_drafts = [ChunkDraft("parent text", page=1), ChunkDraft("child text", page=1, parent=0)]
    doc = db.scalars(select(Document).where(Document.source_path == att.source_path)).one()
    ingest_mod._drop_chunks(db, doc.id)
    assert len(ingest_mod._write_chunks(db, doc.id, monkeypatch_drafts)) == 2
    parent, child = db.scalars(select(DocChunk).where(DocChunk.document_id == doc.id).order_by(DocChunk.id)).all()
    assert child.parent_chunk_id == parent.id and parent.parent_chunk_id is None
    db.rollback()


def test_doc_type_filter_skips_the_rest(policies):
    assert ingest(policies, doc_type="curriculum").ingested == []


# --- the search tool over the ingested corpus ------------------------------------

def test_policy_search_is_full_text_ranked_and_cites_page(db):
    hits = REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "condonation medical grounds"})
    assert hits and {"chunk_id", "document", "section", "page", "excerpt"} <= set(hits[0])
    assert any("Part IV" in h["document"] for h in hits)
    assert all(h["page"] >= 1 for h in hits)
    # stemming: "condoned" reaches the same passages as "condonation"
    assert REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "condoned"})


def test_policy_search_respects_document_audience(db):
    doc = db.scalars(select(Document).where(Document.source_path.like("%code_of_conduct%"))).one()
    doc.audience_roles = ["admin"]
    db.commit()
    try:
        student = REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "ragging"})
        admin = REGISTRY.invoke("search_university_policies", make_ctx("admin"), db, {"query": "ragging"})
        assert not any("Part VII" in h["document"] for h in student)
        assert any("Part VII" in h["document"] for h in admin)
    finally:
        doc.audience_roles = ["student", "faculty", "admin"]
        db.commit()


def test_policy_search_with_no_match_is_empty(db):
    assert REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "quantum chromodynamics"}) == []
