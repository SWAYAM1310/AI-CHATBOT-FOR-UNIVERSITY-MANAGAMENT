"""Manifest-driven ingest: file → `documents` row → `doc_chunks` rows (plan.md §8).

    python -m app.ai.rag.ingest                 # everything in docs/manifest.yaml
    python -m app.ai.rag.ingest --doc-type policy
    python -m app.ai.rag.ingest --force         # re-chunk even if unchanged
    python -m app.ai.rag.ingest --no-embed      # text + tsv only (no Jina calls)

Idempotent: `documents.version` holds the SHA-256 of the file, so an unchanged
file is skipped and a changed one has its chunks replaced. Each document is its
own transaction — one bad PDF does not lose the rest.

Chunking dispatches on `doc_type` through CHUNKERS. This step ships only the
page-level fallback (one chunk per page, no embedding); the clause-aware policy
chunker, the curriculum parent/child chunker and the tabular extractor register
themselves here as they land. `tsv` is populated on every chunk regardless, so
full-text search works from the first ingest.

Embedding is one call per document for late-chunked types (LATE_CHUNKED): the
chunks go up together, in order, so each vector carries the whole document's
context. Other types are embedded in plain batches. Pass `embedder=None` to
skip vectors entirely (offline CI, or a first text-only pass).
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.ai.rag.embedder import Embedder, EmbeddingNotConfigured, get_embedder
from app.ai.rag.manifest import DEFAULT_MANIFEST, ManifestEntry, load_manifest
from app.ai.rag.parsers import ParsedDocument, parse_pdf
from app.db.session import SessionLocal
from app.models import AcademicCalendarEvent, DocChunk, Document

log = logging.getLogger(__name__)

TS_CONFIG = "english"
LATE_CHUNKED = {"policy", "notice"}  # whole document fits one context window


@dataclass(frozen=True)
class ChunkDraft:
    """A chunk before it has a row: what a chunker produces."""

    content: str
    page: int | None = None
    section: str | None = None
    parent: int | None = None  # index into the same draft list, for parent/child chunkers


Chunker = Callable[[ParsedDocument, ManifestEntry], list[ChunkDraft]]


def page_chunks(parsed: ParsedDocument, entry: ManifestEntry) -> list[ChunkDraft]:
    """The fallback: one chunk per non-empty page."""
    return [ChunkDraft(content=p.text, page=p.number) for p in parsed.pages if p.text]


CHUNKERS: dict[str, Chunker] = {}  # doc_type -> chunker; missing types fall back to page_chunks


@dataclass
class IngestReport:
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    chunks: int = 0

    def __str__(self) -> str:
        return (
            f"{len(self.ingested)} ingested ({self.chunks} chunks), "
            f"{len(self.skipped)} unchanged, {len(self.failed)} failed"
        )


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ingest(
    entries: list[ManifestEntry],
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    force: bool = False,
    doc_type: str | None = None,
    embedder: Embedder | None = None,
) -> IngestReport:
    report = IngestReport()
    for entry in entries:
        if doc_type and entry.doc_type != doc_type:
            continue
        with session_factory() as db:
            try:
                n = ingest_one(entry, db, force=force, embedder=embedder)
            except Exception as exc:  # noqa: BLE001 - keep going, report at the end
                db.rollback()
                log.exception("ingest failed for %s", entry.source_path)
                report.failed[entry.source_path] = f"{type(exc).__name__}: {exc}"
                continue
            if n is None:
                report.skipped.append(entry.source_path)
            else:
                report.ingested.append(entry.source_path)
                report.chunks += n
    return report


def ingest_one(
    entry: ManifestEntry, db: Session, *, force: bool = False, embedder: Embedder | None = None
) -> int | None:
    """Ingest a single manifest entry; returns the chunk count, or None if unchanged."""
    digest = file_digest(entry.path)
    doc = db.scalars(select(Document).where(Document.source_path == entry.source_path)).first()
    if doc is not None and doc.version == digest and not force:
        return None

    if doc is None:
        doc = Document(source_path=entry.source_path)
        db.add(doc)
    doc.title = entry.title
    doc.doc_type = entry.doc_type
    doc.category = entry.category
    doc.audience_roles = list(entry.audience_roles)
    doc.effective_date = entry.effective_date
    doc.version = digest
    db.flush()

    parsed = parse_pdf(entry.path)
    drafts = CHUNKERS.get(entry.doc_type, page_chunks)(parsed, entry)
    vectors = _embed(embedder, entry.doc_type, drafts)  # before the drop: an API failure changes nothing
    _drop_chunks(db, doc.id)
    rows = _write_chunks(db, doc.id, drafts, vectors, embedder.model if embedder else None)
    db.commit()
    return rows


def _embed(embedder: Embedder | None, doc_type: str, drafts: list[ChunkDraft]) -> list[list[float]] | None:
    """Vectors for the drafts, or None when running text-only."""
    if embedder is None or not drafts:
        return None
    return embedder.embed_documents([d.content for d in drafts], late_chunking=doc_type in LATE_CHUNKED)


def _drop_chunks(db: Session, document_id: int) -> None:
    ids = select(DocChunk.id).where(DocChunk.document_id == document_id)
    # a calendar row may cite one of these chunks; unlink before the delete
    db.execute(
        update(AcademicCalendarEvent)
        .where(AcademicCalendarEvent.source_chunk_id.in_(ids))
        .values(source_chunk_id=None)
    )
    # children reference parents within the same document: clear the self-FK first
    db.execute(update(DocChunk).where(DocChunk.document_id == document_id).values(parent_chunk_id=None))
    db.execute(delete(DocChunk).where(DocChunk.document_id == document_id))


def _write_chunks(
    db: Session,
    document_id: int,
    drafts: list[ChunkDraft],
    vectors: list[list[float]] | None = None,
    model: str | None = None,
) -> int:
    rows: list[DocChunk] = []
    for i, d in enumerate(drafts):
        row = DocChunk(
            document_id=document_id,
            section=d.section,
            page=d.page,
            content=d.content,
            tsv=func.to_tsvector(TS_CONFIG, d.content),
            embedding=vectors[i] if vectors else None,
            embedding_model=model if vectors else None,
        )
        db.add(row)
        rows.append(row)
    db.flush()  # ids exist now; resolve parent links by draft index
    for d, row in zip(drafts, rows):
        if d.parent is not None:
            row.parent_chunk_id = rows[d.parent].id
    db.flush()
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--doc-type", choices=("policy", "curriculum", "tabular", "notice"))
    ap.add_argument("--force", action="store_true", help="re-chunk unchanged files too")
    ap.add_argument("--no-embed", action="store_true", help="skip vectors (text + tsv only)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    embedder: Embedder | None = None
    if not args.no_embed:
        try:
            embedder = get_embedder()
        except EmbeddingNotConfigured as exc:
            print(f"warning: {exc}; ingesting text only (use --no-embed to silence)", file=sys.stderr)

    entries = load_manifest(args.manifest)
    report = ingest(entries, force=args.force, doc_type=args.doc_type, embedder=embedder)
    if embedder is not None:
        print(f"embedded with {embedder.model}: {getattr(embedder, 'calls', '?')} calls, "
              f"{getattr(embedder, 'tokens_used', '?')} tokens")
    for path in report.ingested:
        print(f"ingested  {path}")
    for path in report.skipped:
        print(f"unchanged {path}")
    for path, err in report.failed.items():
        print(f"FAILED    {path}: {err}")
    print(report)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
