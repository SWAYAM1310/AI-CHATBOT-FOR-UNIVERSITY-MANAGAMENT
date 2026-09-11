"""Phase 3 step 2 — the Jina API embedder and the offline fake.

The real client is exercised against an httpx MockTransport: what goes on the
wire (task, late_chunking, batching, retries) is the contract, not the vectors.
"""
from __future__ import annotations

import json
import math

import httpx
import pytest
from sqlalchemy import select

from app.ai.rag import embedder as embedder_mod
from app.ai.rag.embedder import (
    BATCH,
    EmbeddingError,
    EmbeddingNotConfigured,
    FakeEmbedder,
    JinaEmbedder,
    api_model_name,
    get_embedder,
)
from app.ai.rag.ingest import ingest, ingest_one
from app.ai.rag.manifest import load_manifest
from app.config import settings
from app.db.session import SessionLocal
from app.models import DocChunk, Document

DIM = 8


class FakeJina:
    """Records requests; answers with unit vectors of DIM (or whatever `respond` says)."""

    def __init__(self, respond=None) -> None:
        self.requests: list[dict] = []
        self.respond = respond or self._ok

    @staticmethod
    def _ok(body: dict, n: int) -> httpx.Response:
        data = [{"index": i, "embedding": [1.0 if j == i % DIM else 0.0 for j in range(DIM)]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data, "usage": {"total_tokens": 7 * len(body["input"])}})

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        return self.respond(body, len(self.requests))

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="https://jina.test/v1", transport=httpx.MockTransport(self.handler))


def make(fake: FakeJina, **kw) -> JinaEmbedder:
    sleeps: list[float] = []
    emb = JinaEmbedder(api_key="k", model="jinaai/jina-embeddings-v5-omni-small", dim=DIM, client=fake.client(),
                       sleeper=sleeps.append, **kw)
    emb.sleeps = sleeps  # type: ignore[attr-defined]
    return emb


# --- wire contract ------------------------------------------------------------

def test_model_name_drops_the_hf_prefix():
    assert api_model_name("jinaai/jina-embeddings-v5-omni-small") == "jina-embeddings-v5-omni-small"
    assert api_model_name("jina-embeddings-v3") == "jina-embeddings-v3"


def test_query_and_passage_tasks_are_never_mixed_up():
    fake = FakeJina()
    emb = make(fake)
    emb.embed_query("hello")
    emb.embed_documents(["a", "b"])
    assert [r["task"] for r in fake.requests] == ["retrieval.query", "retrieval.passage"]
    assert "late_chunking" not in fake.requests[1]


def test_late_chunking_sends_the_whole_document_in_one_request():
    fake = FakeJina()
    emb = make(fake)
    chunks = [f"chunk {i}" for i in range(BATCH + 5)]
    vecs = emb.embed_documents(chunks, late_chunking=True)
    assert len(fake.requests) == 1 and fake.requests[0]["late_chunking"] is True
    assert fake.requests[0]["input"] == chunks and len(vecs) == len(chunks)


def test_plain_documents_are_batched():
    fake = FakeJina()
    emb = make(fake)
    vecs = emb.embed_documents([f"c{i}" for i in range(BATCH * 2 + 1)])
    assert [len(r["input"]) for r in fake.requests] == [BATCH, BATCH, 1]
    assert len(vecs) == BATCH * 2 + 1 and emb.tokens_used == 7 * (BATCH * 2 + 1)


def test_query_cache_makes_repeat_questions_free():
    fake = FakeJina()
    emb = make(fake)
    a = emb.embed_query("What is the attendance rule?")
    b = emb.embed_query("  what is the attendance rule? ")
    assert a == b and len(fake.requests) == 1


def test_429_and_5xx_are_retried_with_backoff_then_succeed():
    def respond(body, n):
        if n == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, text="slow down")
        if n == 2:
            return httpx.Response(503, text="busy")
        return FakeJina._ok(body, n)

    fake = FakeJina(respond)
    emb = make(fake)
    assert len(emb.embed_query("x")) == DIM
    assert len(fake.requests) == 3
    assert emb.sleeps[0] == 2.0 and emb.sleeps[1] > 0  # honoured Retry-After, then jittered backoff


def test_retries_are_bounded_and_4xx_is_not_retried():
    fake = FakeJina(lambda body, n: httpx.Response(429, text="no"))
    with pytest.raises(EmbeddingError, match="429"):
        make(fake, max_retries=2).embed_query("x")
    assert len(fake.requests) == 3

    fake = FakeJina(lambda body, n: httpx.Response(401, text="bad key"))
    with pytest.raises(EmbeddingError, match="401"):
        make(fake).embed_query("x")
    assert len(fake.requests) == 1


def test_malformed_responses_are_errors_not_garbage_vectors():
    fake = FakeJina(lambda body, n: httpx.Response(200, json={"data": [], "usage": {}}))
    with pytest.raises(EmbeddingError, match="0 vectors"):
        make(fake).embed_query("x")
    fake = FakeJina(lambda body, n: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}))
    with pytest.raises(EmbeddingError, match="dimension"):
        make(fake).embed_query("x")


def test_vectors_come_back_in_input_order_even_if_the_api_shuffles():
    def respond(body, n):
        data = [{"index": i, "embedding": [float(i)] * DIM} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": list(reversed(data)), "usage": {}})

    vecs = make(FakeJina(respond)).embed_documents(["a", "b", "c"])
    assert [v[0] for v in vecs] == [0.0, 1.0, 2.0]


def test_no_key_means_no_embedder(monkeypatch):
    with pytest.raises(EmbeddingNotConfigured):
        JinaEmbedder(api_key="")
    monkeypatch.setattr(settings, "jina_api_key", "")
    monkeypatch.setattr(embedder_mod, "_default", None)
    with pytest.raises(EmbeddingNotConfigured):
        get_embedder()
    assert embedder_mod._default is None


# --- the fake ------------------------------------------------------------------

def test_fake_embedder_is_deterministic_and_term_sensitive():
    f = FakeEmbedder(dim=64)
    a, b = f.embed_query("attendance requirement percent"), f.embed_query("attendance requirement percent")
    c = f.embed_query("attendance percent required")
    d = f.embed_query("hostel mess charges")
    cos = lambda x, y: sum(p * q for p, q in zip(x, y))  # noqa: E731 - unit vectors
    assert a == b and math.isclose(cos(a, a), 1.0, abs_tol=1e-9)
    assert cos(a, c) > cos(a, d)
    assert len(f.embed_documents(["x", "y"], late_chunking=True)) == 2


# --- ingest with vectors ---------------------------------------------------------

@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


def _attendance():
    return next(e for e in load_manifest() if e.path.name == "attendance_regulations.pdf")


def test_ingest_writes_vectors_and_model_and_late_chunks_policies(db):
    fake = FakeEmbedder()
    assert ingest_one(_attendance(), db, force=True, embedder=fake) == 40  # clause chunks
    doc = db.scalars(select(Document).where(Document.source_path == _attendance().source_path)).one()
    chunks = db.scalars(select(DocChunk).where(DocChunk.document_id == doc.id)).all()
    assert all(c.embedding is not None and len(c.embedding) == settings.embedding_dim for c in chunks)
    assert {c.embedding_model for c in chunks} == {"fake"}
    assert fake.calls == 1  # one late-chunked call for the whole policy

    # a nearest-neighbour query over the fake vectors lands among the condonation clauses
    # (a hashed bag-of-words fake: the short preamble can sneak into the top few on a collision)
    v = fake.embed_query("condonation medical grounds hospitalisation certificate")
    nearest = db.scalars(
        select(DocChunk.section).where(DocChunk.document_id == doc.id).order_by(DocChunk.embedding.cosine_distance(v)).limit(3)
    ).all()
    assert sum(s.startswith("§5.") for s in nearest) >= 2, nearest


def test_ingest_without_an_embedder_leaves_vectors_null(db):
    assert ingest_one(_attendance(), db, force=True, embedder=None) == 40
    doc = db.scalars(select(Document).where(Document.source_path == _attendance().source_path)).one()
    assert db.scalar(select(DocChunk.embedding).where(DocChunk.document_id == doc.id).limit(1)) is None


def test_embedding_failure_keeps_the_previous_chunks(db):
    ingest_one(_attendance(), db, force=True, embedder=FakeEmbedder())
    doc = db.scalars(select(Document).where(Document.source_path == _attendance().source_path)).one()
    before = sorted(db.scalars(select(DocChunk.id).where(DocChunk.document_id == doc.id)))

    class Exploding(FakeEmbedder):
        def embed_documents(self, texts, *, late_chunking=False):
            raise EmbeddingError("quota")

    report = ingest([_attendance()], force=True, embedder=Exploding())
    assert "quota" in report.failed[_attendance().source_path]
    db.expire_all()
    assert sorted(db.scalars(select(DocChunk.id).where(DocChunk.document_id == doc.id))) == before
