"""Phase 3 step 4 — hybrid retriever (dense ∪ sparse → RRF) and citations.

Runs against the 7 policy PDFs ingested with the FakeEmbedder (deterministic
hashed bag-of-words), so the dense branch is exercised offline. Ranking
quality with real Jina vectors was checked by hand at build time; what is
pinned here is the mechanism: both branches contribute, fusion orders by
combined rank, the audience filter holds in both, and degradation is graceful.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.ai.rag import retriever as retriever_mod
from app.ai.rag.citations import resolve
from app.ai.rag.embedder import EmbeddingNotConfigured, FakeEmbedder
from app.ai.rag.ingest import ChunkDraft, ingest, _drop_chunks, _write_chunks
from app.ai.rag.manifest import load_manifest
from app.ai.rag.retriever import Hit, retrieve, rrf
from app.ai.tools.registry import REGISTRY
from app.db.session import SessionLocal
from app.models import DocChunk, Document
from tests.conftest import make_ctx

FAKE = FakeEmbedder()


@pytest.fixture(scope="module", autouse=True)
def _ingested_with_fake_vectors():
    policies = [e for e in load_manifest() if e.doc_type == "policy"]
    with SessionLocal() as db:
        db.execute(text("UPDATE academic_calendar SET source_chunk_id = NULL"))
        db.execute(text("TRUNCATE doc_chunks, documents RESTART IDENTITY CASCADE"))
        db.commit()
    report = ingest(policies, embedder=FAKE)
    assert not report.failed, report.failed
    retriever_mod._warned_no_embedder = False


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


# --- fusion ------------------------------------------------------------------------

def test_rrf_rewards_presence_on_both_lists_and_high_rank():
    scores = rrf([[1, 2, 3], [3, 4, 1]], k=60)
    assert scores[1] == pytest.approx(1 / 61 + 1 / 63)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)
    assert scores[2] == pytest.approx(1 / 62) and scores[4] == pytest.approx(1 / 62)
    assert sorted(scores, key=scores.get, reverse=True)[:2] == [1, 3]  # on both lists beats rank-2 on one


def test_hits_carry_both_ranks_and_fused_score(db):
    hits = retrieve(db, "condonation medical grounds hospitalisation", role="student", embedder=FAKE)
    assert hits and all(isinstance(h, Hit) for h in hits)
    assert any(h.dense_rank and h.sparse_rank for h in hits)  # at least one chunk on both lists
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    top = hits[0]
    assert top.document.startswith("Academic Regulations") and top.section.startswith("§5.")
    assert top.parent_content is None  # policy chunks have no parent


def test_dense_and_sparse_each_contribute(db, monkeypatch):
    q = "condonation medical grounds hospitalisation"
    both = [h.chunk_id for h in retrieve(db, q, role="student", k=8, embedder=FAKE)]
    monkeypatch.setattr(retriever_mod, "_dense_candidates", lambda *a, **k: [])
    sparse_only = [h.chunk_id for h in retrieve(db, q, role="student", k=8, embedder=FAKE)]
    monkeypatch.undo()
    monkeypatch.setattr(retriever_mod, "_sparse_candidates", lambda *a, **k: [])
    dense_only = [h.chunk_id for h in retrieve(db, q, role="student", k=8, embedder=FAKE)]
    assert sparse_only and dense_only
    assert set(both) & set(sparse_only) and set(both) & set(dense_only)
    assert both != sparse_only and both != dense_only  # fusion is not either branch alone


def test_sparse_falls_back_to_an_or_query_for_long_questions(db, monkeypatch):
    monkeypatch.setattr(retriever_mod, "_dense_candidates", lambda *a, **k: [])
    q = "what attendance percentage do I need to be allowed to sit the end-semester examination"
    hits = retrieve(db, q, role="student", embedder=FAKE)
    assert hits, "AND-query is empty for this phrasing; the OR fallback must fill in"
    assert any(h.section.startswith("§4.") for h in hits)  # the eligibility section


def test_without_an_embedder_retrieval_is_sparse_only(db, monkeypatch, caplog):
    class NoKey:
        def embed_query(self, text):
            raise EmbeddingNotConfigured("JINA_API_KEY is not set")

    monkeypatch.setattr(retriever_mod, "_warned_no_embedder", False)
    with caplog.at_level("WARNING", logger="app.ai.rag.retriever"):
        hits = retrieve(db, "ragging", role="student", embedder=NoKey())
        retrieve(db, "ragging", role="student", embedder=NoKey())
    assert hits and all(h.dense_rank is None and h.sparse_rank for h in hits)
    assert sum("dense retrieval unavailable" in r.message for r in caplog.records) == 1  # warned once


def test_empty_query_and_no_sparse_match_are_empty(db, monkeypatch):
    assert retrieve(db, "   ", role="student", embedder=FAKE) == []
    monkeypatch.setattr(retriever_mod, "_dense_candidates", lambda *a, **k: [])
    assert retrieve(db, "the of and", role="student", embedder=FAKE) == []  # stopwords only: empty tsquery, no crash
    assert retrieve(db, "quantum chromodynamics", role="student", embedder=FAKE) == []


# --- filters ---------------------------------------------------------------------------

def test_audience_filter_applies_to_both_branches(db):
    doc = db.scalars(select(Document).where(Document.source_path.like("%code_of_conduct%"))).one()
    doc.audience_roles = ["admin"]
    db.commit()
    try:
        student = retrieve(db, "ragging", role="student", embedder=FAKE)
        admin = retrieve(db, "ragging", role="admin", embedder=FAKE)
        assert not any(h.document_id == doc.id for h in student)
        assert any(h.document_id == doc.id for h in admin)
    finally:
        doc.audience_roles = ["student", "faculty", "admin"]
        db.commit()


def test_doc_type_filter(db):
    assert retrieve(db, "attendance", role="student", doc_types=("curriculum",), embedder=FAKE) == []
    assert retrieve(db, "attendance", role="student", doc_types=("policy", "notice"), embedder=FAKE)


def test_parent_content_is_hydrated_for_child_chunks(db):
    doc = db.scalars(select(Document).where(Document.source_path.like("%student_services%"))).one()
    drafts = [
        ChunkDraft("CS301 Database Systems: course record for hydration", page=1, section="CS301"),
        ChunkDraft("Unit 3 normalisation zebra-token", page=2, section="CS301 / Unit 3", parent=0),
    ]
    _drop_chunks(db, doc.id)
    _write_chunks(db, doc.id, drafts, FAKE.embed_documents([d.content for d in drafts]), "fake")
    db.flush()
    (hit,) = [h for h in retrieve(db, "zebra-token normalisation", role="student", embedder=FAKE) if h.section == "CS301 / Unit 3"]
    assert hit.parent_content.startswith("CS301 Database Systems")
    assert hit.as_passage()["parent"].startswith("CS301")
    db.rollback()


# --- the tool over the retriever -------------------------------------------------------

def test_policy_tool_returns_whole_clauses_in_the_citation_shape(db, monkeypatch):
    monkeypatch.setattr(retriever_mod, "get_embedder", lambda: FAKE)
    hits = REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "condonation medical grounds"})
    assert hits and {"chunk_id", "document", "section", "page", "excerpt"} <= set(hits[0])
    assert "parent" not in hits[0]
    clause = db.get(DocChunk, hits[0]["chunk_id"])
    assert hits[0]["excerpt"] == clause.content  # the whole clause, not a 300-char cut


# --- citations -------------------------------------------------------------------------

PASSAGES = [
    {"chunk_id": 11, "document": "Part IV", "section": "§4.2 Minimum attendance", "page": 2, "excerpt": "x" * 400},
    {"chunk_id": 12, "document": "Part IV", "section": "§5.2 Condonation", "page": 2, "excerpt": "at least 65"},
]


def test_citations_are_numbered_in_first_cited_order_and_deduplicated():
    text_, cites = resolve("Need 75% [[cite:11]]. Condonable [[cite:12]]. Still 75% [[cite:11]].", PASSAGES)
    assert text_ == "Need 75% [1]. Condonable [2]. Still 75% [1]."
    assert [(c["n"], c["chunk_id"], c["section"], c["page"]) for c in cites] == [
        (1, 11, "§4.2 Minimum attendance", 2),
        (2, 12, "§5.2 Condonation", 2),
    ]
    assert len(cites[0]["snippet"]) == 300 and cites[1]["snippet"] == "at least 65"


def test_unknown_markers_are_dropped_and_spacing_tidied():
    text_, cites = resolve("Rule [[cite:99]] applies [[cite: 12 ]].", PASSAGES)
    assert text_ == "Rule applies [1]."
    assert [c["chunk_id"] for c in cites] == [12]


def test_text_without_markers_is_untouched():
    assert resolve("Hello there.", PASSAGES) == ("Hello there.", [])
    assert resolve("No passages [[cite:11]]", []) == ("No passages", [])
