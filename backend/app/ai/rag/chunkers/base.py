"""What a chunker produces and where it registers.

Kept apart from `ingest.py` so chunkers can import it without a cycle (and so
`python -m app.ai.rag.ingest` and `import app.ai.rag.ingest` share one registry).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.ai.rag.manifest import ManifestEntry
from app.ai.rag.parsers import ParsedDocument


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
