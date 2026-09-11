"""Per-doc-type chunkers (plan.md §8). Importing this package registers them
into `base.CHUNKERS`, which `ingest` reads at dispatch time."""
from __future__ import annotations

from app.ai.rag.chunkers import curriculum, policy  # noqa: F401  (register "curriculum", "policy")
from app.ai.rag.chunkers.base import CHUNKERS, EXTRACTORS, Chunker, ChunkDraft, page_chunks

__all__ = ["CHUNKERS", "EXTRACTORS", "Chunker", "ChunkDraft", "page_chunks"]
