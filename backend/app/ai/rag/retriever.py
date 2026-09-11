"""Hybrid retrieval over `doc_chunks` (plan.md §8 "Retrieval").

Two candidate lists, fused:

- dense   — pgvector cosine distance against the Jina query embedding
- sparse  — Postgres full-text search. `websearch_to_tsquery` ANDs every term,
            which is precise when it hits and empty for a long natural-language
            question, so when it under-fills the list is topped up with an
            OR-query over the same terms ranked by `ts_rank_cd`.

Reciprocal Rank Fusion (k=60) merges the two: a chunk near the top of either
list scores well, a chunk on both lists scores best. Neither branch's raw
score is comparable to the other's, which is why ranks are fused, not scores.

Both branches carry the audience pre-filter (`documents.audience_roles`) in SQL
so a role never sees a candidate it is not allowed to read — the RBAC Layer-1
rule for documents. `doc_types` narrows further (the policy tool asks for
policy + notice; the curriculum tools will ask for curriculum).

Parent hydration: a child chunk (curriculum unit) carries its parent's text
(the course record) in `parent_content`, so the synthesis prompt sees the unit
in context. Policy chunks have no parent and the field stays None.

Without a Jina key the dense branch is skipped with a warning and retrieval
is sparse-only — the system degrades, it does not fail.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import Select, desc, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.ai.rag.embedder import Embedder, EmbeddingError, get_embedder
from app.ai.rag.ingest import TS_CONFIG
from app.models import DocChunk, Document

log = logging.getLogger(__name__)

TOP_K = 5
CANDIDATES = 20  # per branch, before fusion
RRF_K = 60  # the constant from the RRF paper; larger = flatter, less rank-1 dominance
CONTENT_CHARS = 1500  # a policy clause is ~300; a syllabus unit can run longer

_TERM = re.compile(r"[a-z0-9]+")
_warned_no_embedder = False


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    document_id: int
    document: str
    doc_type: str
    section: str | None
    page: int | None
    content: str
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    parent_content: str | None = None

    def as_passage(self) -> dict:
        """The shape the tools and the synthesis prompt work with."""
        return {
            "chunk_id": self.chunk_id,
            "document": self.document,
            "section": self.section,
            "page": self.page,
            "excerpt": self.content[:CONTENT_CHARS],
            **({"parent": self.parent_content[:CONTENT_CHARS]} if self.parent_content else {}),
        }


def rrf(ranked_lists: Iterable[Sequence[int]], *, k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion: id -> sum over lists of 1 / (k + rank), rank 1-based."""
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def retrieve(
    db: Session,
    query: str,
    *,
    role: str,
    k: int = TOP_K,
    candidates: int = CANDIDATES,
    doc_types: Sequence[str] | None = None,
    exclude_sections: Sequence[str] | None = None,
    embedder: Embedder | None = None,
) -> list[Hit]:
    """Top-k chunks for `query` that `role` may read, dense ∪ sparse fused by RRF."""
    query = query.strip()
    if not query:
        return []

    def base() -> Select:
        stmt = (
            select(DocChunk.id)
            .join(Document, Document.id == DocChunk.document_id)
            .where(Document.audience_roles.any(role))
        )
        if doc_types:
            stmt = stmt.where(Document.doc_type.in_(list(doc_types)))
        if exclude_sections:  # e.g. a syllabus's programme-structure pages: big, and answered exactly elsewhere
            stmt = stmt.where(or_(DocChunk.section.is_(None), DocChunk.section.not_in(list(exclude_sections))))
        return stmt

    dense = _dense_candidates(db, base(), query, candidates, embedder)
    sparse = _sparse_candidates(db, base(), query, candidates)
    if not dense and not sparse:
        return []

    scores = rrf([lst for lst in (dense, sparse) if lst])
    order = sorted(scores, key=lambda cid: (-scores[cid], cid))[:k]
    rows = _hydrate(db, order)
    dense_pos = {cid: i for i, cid in enumerate(dense, start=1)}
    sparse_pos = {cid: i for i, cid in enumerate(sparse, start=1)}
    return [
        Hit(
            chunk_id=r.id,
            document_id=r.document_id,
            document=r.title,
            doc_type=r.doc_type,
            section=r.section,
            page=r.page,
            content=r.content,
            score=scores[r.id],
            dense_rank=dense_pos.get(r.id),
            sparse_rank=sparse_pos.get(r.id),
            parent_content=r.parent_content,
        )
        for r in rows
    ]


def _dense_candidates(db: Session, base: Select, query: str, n: int, embedder: Embedder | None) -> list[int]:
    global _warned_no_embedder
    try:
        vec = (embedder or get_embedder()).embed_query(query)
    except EmbeddingError as exc:
        if not _warned_no_embedder:
            log.warning("dense retrieval unavailable (%s); sparse only", exc)
            _warned_no_embedder = True
        return []
    stmt = (
        base.where(DocChunk.embedding.is_not(None))
        .order_by(DocChunk.embedding.cosine_distance(vec), DocChunk.id)
        .limit(n)
    )
    return list(db.scalars(stmt))


def _sparse_candidates(db: Session, base: Select, query: str, n: int) -> list[int]:
    def ranked(tsq) -> list[int]:
        stmt = (
            base.where(DocChunk.tsv.op("@@")(tsq))
            .order_by(desc(func.ts_rank_cd(DocChunk.tsv, tsq)), DocChunk.id)
            .limit(n)
        )
        return list(db.scalars(stmt))

    out = ranked(func.websearch_to_tsquery(TS_CONFIG, query))
    if len(out) < n:
        terms = _TERM.findall(query.lower())
        if terms:
            # to_tsquery stems and drops stopwords itself; a stopword-only query yields an empty tsquery
            seen = set(out)
            for cid in ranked(func.to_tsquery(TS_CONFIG, " | ".join(terms))):
                if cid not in seen:
                    out.append(cid)
                    seen.add(cid)
    return out[:n]


def _hydrate(db: Session, chunk_ids: list[int]):
    if not chunk_ids:
        return []
    parent = aliased(DocChunk)
    rows = db.execute(
        select(
            DocChunk.id,
            DocChunk.document_id,
            DocChunk.section,
            DocChunk.page,
            DocChunk.content,
            Document.title,
            Document.doc_type,
            parent.content.label("parent_content"),
        )
        .join(Document, Document.id == DocChunk.document_id)
        .outerjoin(parent, parent.id == DocChunk.parent_chunk_id)
        .where(DocChunk.id.in_(chunk_ids))
    ).all()
    by_id = {r.id: r for r in rows}
    return [by_id[cid] for cid in chunk_ids if cid in by_id]
