"""Chunker + extractor for `tabular` documents (plan.md §8 "tabular").

"Extract, don't embed": the value of a table is exact rows, so a `calendar`
document's rows are upserted into `academic_calendar` (keyed on event +
start date) with `source_chunk_id`, and date questions are answered by
`get_academic_calendar`, not by similarity search. The chunks still exist —
one per page of prose and one per table, each row rendered as a sentence —
as the low-priority fallback that lets retrieval land on the calendar when
the router did not call the tool.

Tables that continue over a page break arrive without a header; they inherit
the previous table's header when the widths agree.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.rag.chunkers.base import CHUNKERS, EXTRACTORS, ChunkDraft, page_chunks
from app.ai.rag.manifest import ManifestEntry
from app.ai.rag.parsers import ParsedDocument, Table, extract_tables
from app.models import AcademicCalendarEvent, Document

log = logging.getLogger(__name__)

_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")
_HEADER_HINTS = ("event", "from", "start", "date")

# header cell (lowercased, first word) -> academic_calendar column
_CALENDAR_COLUMNS = {
    "event": "event",
    "type": "event_type",
    "from": "start_date",
    "start": "start_date",
    "date": "start_date",
    "to": "end_date",
    "end": "end_date",
    "applies": "applies_to",
    "term": "term",
}


@dataclass
class TableBlock:
    table: Table
    header: list[str] | None
    draft: int  # index of this table's chunk


def parse_date(text: str) -> date | None:
    text = " ".join(text.split())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _is_header(row: list[str]) -> bool:
    cells = [c.lower() for c in row]
    return "event" in cells and any(any(h in c for h in _HEADER_HINTS[1:]) for c in cells)


def _row_sentence(header: list[str] | None, row: list[str]) -> str:
    if header:
        return "; ".join(f"{h}: {v}" for h, v in zip(header, row) if v)
    return " | ".join(v for v in row if v)


def build(parsed: ParsedDocument, entry: ManifestEntry) -> tuple[list[ChunkDraft], list[TableBlock]]:
    """Page chunks for the prose plus one chunk per table (rows as sentences)."""
    drafts = page_chunks(parsed, entry)
    blocks: list[TableBlock] = []
    header: list[str] | None = None
    for n, table in enumerate(extract_tables(parsed.path), start=1):
        rows = table.rows
        if rows and _is_header(rows[0]):
            header, rows = rows[0], rows[1:]
        elif header is not None and rows and len(rows[0]) != len(header):
            header = None  # a different table; do not label its columns with a stale header
        if not rows:
            continue
        lines = [_row_sentence(header, r) for r in rows]
        head = f"Table {n}" + (f" ({', '.join(header)})" if header else "")
        blocks.append(TableBlock(table=table, header=header, draft=len(drafts)))
        drafts.append(ChunkDraft(content=f"{head}\n" + "\n".join(lines), page=table.page, section=head))
    return drafts, blocks


def tabular_chunks(parsed: ParsedDocument, entry: ManifestEntry) -> list[ChunkDraft]:
    return build(parsed, entry)[0]


# --- calendar extract -----------------------------------------------------------------

def extract_calendar(db: Session, document: Document, parsed: ParsedDocument, entry: ManifestEntry, rows: list) -> int:
    """Upsert `academic_calendar` from a calendar document's tables; returns rows written."""
    if entry.category != "calendar":
        return 0
    _, blocks = build(parsed, entry)
    written = 0
    for block in blocks:
        if not block.header:
            continue
        columns = [_CALENDAR_COLUMNS.get(h.lower().split()[0] if h else "", None) for h in block.header]
        if "event" not in columns or "start_date" not in columns:
            continue
        for raw in block.table.rows:
            if _is_header(raw):
                continue
            record = {c: v.strip() for c, v in zip(columns, raw) if c}
            start = parse_date(record.get("start_date", ""))
            if not record.get("event") or start is None:
                log.warning("calendar row skipped (no event/date): %s", raw)
                continue
            end = parse_date(record.get("end_date", "")) if record.get("end_date") else None
            term = re.sub(r"\s+", "", record.get("term", "")) or None
            row = db.scalars(
                select(AcademicCalendarEvent).where(
                    AcademicCalendarEvent.event == record["event"], AcademicCalendarEvent.start_date == start
                )
            ).first()
            if row is None:
                row = AcademicCalendarEvent(event=record["event"], start_date=start)
                db.add(row)
            row.event_type = record.get("event_type") or row.event_type or "event"
            row.end_date = end
            row.applies_to = record.get("applies_to") or row.applies_to
            row.term = term or row.term
            row.source_chunk_id = rows[block.draft].id
            written += 1
    db.flush()
    return written


CHUNKERS["tabular"] = tabular_chunks
EXTRACTORS["tabular"] = extract_calendar
