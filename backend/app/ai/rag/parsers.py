"""PDF → text, page by page (plan.md §8 "Parsing").

PyMuPDF for text with reading order, pdfplumber for tables. Every string that
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
            doc.pages.append(Page(number=i, text=normalize(page.get_text("text"))))
    return doc


def extract_tables(path: Path, *, pages: list[int] | None = None) -> list[Table]:
    """Tables as rows of normalised cell strings — for `tabular` documents.

    Imported lazily: pdfplumber is slow to import and only tabular ingest needs it.
    """
    import pdfplumber

    out: list[Table] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            if pages is not None and i not in pages:
                continue
            for table in page.extract_tables():
                rows = [[normalize(cell or "") for cell in row] for row in table]
                rows = [r for r in rows if any(r)]
                if rows:
                    out.append(Table(page=i, rows=rows))
    return out
