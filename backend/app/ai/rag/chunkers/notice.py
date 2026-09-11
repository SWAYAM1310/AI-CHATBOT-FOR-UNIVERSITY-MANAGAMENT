"""Chunker for `notice` documents (plan.md §8): one chunk, the whole notice.

A notice is a page or so of prose about one thing; splitting it would only
separate the date from the deadline it explains. `section` is the notice's
own heading (its first line), so a citation reads "Notice FO/N/2026/07 …".
"""
from __future__ import annotations

from app.ai.rag.chunkers.base import CHUNKERS, ChunkDraft
from app.ai.rag.manifest import ManifestEntry
from app.ai.rag.parsers import ParsedDocument


def notice_chunks(parsed: ParsedDocument, entry: ManifestEntry) -> list[ChunkDraft]:
    text = parsed.text
    if not text:
        return []
    heading = text.split("\n", 1)[0].strip()
    first_page = next((p.number for p in parsed.pages if p.text), 1)
    return [ChunkDraft(content=text, page=first_page, section=heading[:200] or None)]


CHUNKERS["notice"] = notice_chunks
