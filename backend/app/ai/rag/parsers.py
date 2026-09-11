"""PDF → text, page by page (plan.md §8 "Parsing").

PyMuPDF for text with reading order and for tables. Every string that
leaves this module is NFKC-normalised: PDF fonts emit ligatures (`ﬃ`, `ﬁ`) and
odd spaces, and an un-normalised "eﬃcient" neither tokenises for full-text
search nor matches a user's query.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

_WS = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()


@dataclass(frozen=True)
class Page:
    number: int  # 1-based, as a reader would cite it
    text: str


@dataclass(frozen=True)
class Table:
    page: int
    rows: list[list[str]]


@dataclass
class ParsedDocument:
    path: Path
    pages: list[Page] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def parse_pdf(path: Path) -> ParsedDocument:
    """All pages, in order, empty pages included (so page numbers stay honest)."""
    doc = ParsedDocument(path=path)
    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf, start=1):
            doc.pages.append(Page(number=i, text=normalize(page.get_text("text", sort=True))))
    return doc


def extract_tables(path: Path, *, pages: list[int] | None = None) -> list[Table]:
    """Tables as rows of normalised cell strings — for `tabular` documents.

    PyMuPDF's table finder keeps the row at the top of a page when a table runs
    over a page break (pdfplumber dropped it). The raw grid still needs
    `clean_tables()`: a continued table comes back with phantom empty columns
    and a wrapped cell can split one row into two.
    """
    out: list[Table] = []
    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf, start=1):
            if pages is not None and i not in pages:
                continue
            for table in page.find_tables().tables:
                rows = [[normalize(cell or "").replace("\n", " ") for cell in row] for row in table.extract()]
                rows = [r for r in rows if any(r)]
                if rows:
                    out.append(Table(page=i, rows=rows))
    return clean_tables(out)


def clean_tables(tables: list[Table]) -> list[Table]:
    """Undo the two artefacts a page-broken table shows: phantom columns and split rows.

    - a column that is empty in every row of a table is a ruling artefact, not data
    - a row whose first cell is empty continues the row above (a wrapped cell)
    """
    cleaned: list[Table] = []
    for t in tables:
        width = max(len(r) for r in t.rows)
        rows = [r + [""] * (width - len(r)) for r in t.rows]
        keep = [j for j in range(width) if any(r[j] for r in rows)]
        rows = [[r[j] for j in keep] for r in rows]
        merged: list[list[str]] = []
        for r in rows:
            if merged and not r[0]:
                merged[-1] = [f"{a} {b}".strip() if b else a for a, b in zip(merged[-1], r)]
            else:
                merged.append(r)
        if merged:
            cleaned.append(Table(page=t.page, rows=merged))
    return cleaned
