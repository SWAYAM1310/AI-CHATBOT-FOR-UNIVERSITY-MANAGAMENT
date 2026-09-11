"""Clause-aware chunker for `policy` documents (plan.md §8 "policy").

The policy corpus is numbered regulation text:

    1. Purpose and scope            <- section heading
    1.1 These regulations govern ...  <- clause
    5.3.1 Medical grounds - ...       <- sub-clause

One chunk per top-level clause, sub-clauses folded in, the section heading
repeated on top so the chunk reads (and ranks) on its own. `section` is what a
citation shows - "§4.2 Minimum attendance for examination eligibility" - and
`page` is the page the clause starts on, taken from where the line came from
rather than by searching for the text again.

The PDF text is a flat stream: table cells come out one per line, and a wrapped
sentence can start with a number ("5, except that...", "3.6."). A leading number
is therefore only a heading or clause when it is the *next one in sequence*;
anything else is continuation text of the clause above.

Clauses beyond TARGET_TOKENS are split at sub-clause boundaries, then by
sentence, and labelled "§5.3 (2/3)". The title block before section 1 becomes
a "Preamble" chunk so document-ref / effective-date questions have a home.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.rag.chunkers.base import CHUNKERS, ChunkDraft
from app.ai.rag.manifest import ManifestEntry
from app.ai.rag.parsers import ParsedDocument

TARGET_TOKENS = 400
CHARS_PER_TOKEN = 4  # rough English average; "about 400" is all we need

_SECTION = re.compile(r"^(\d+)\.\s+(\S.*)$")
_CLAUSE = re.compile(r"^(\d+(?:\.\d+)+)\s+(\S.*)$")
_SENTENCE_END = re.compile(r"(?<=[.;:])\s+(?=[A-Z(‘“\"'])")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class Clause:
    number: tuple[int, ...]  # (4, 2) or (5, 3, 1); (N, 0) = unnumbered lead-in under heading N
    page: int
    lines: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return ".".join(map(str, self.number))

    @property
    def text(self) -> str:
        return " ".join(self.lines)

    @property
    def is_top(self) -> bool:
        return len(self.number) == 2


@dataclass
class Section:
    number: int
    title: str
    page: int
    clauses: list[Clause] = field(default_factory=list)

    @property
    def heading(self) -> str:
        return f"{self.number}. {self.title}"


@dataclass
class Outline:
    preamble: list[tuple[int, str]] = field(default_factory=list)  # (page, line)
    sections: list[Section] = field(default_factory=list)


def parse_outline(parsed: ParsedDocument) -> Outline:
    """Sections and clauses with the page each starts on, sequence-validated."""
    outline = Outline()
    section: Section | None = None

    for page in parsed.pages:
        for line in page.text.split("\n"):
            if not line:
                continue

            m = _SECTION.match(line)
            if m and int(m.group(1)) == len(outline.sections) + 1:
                section = Section(number=int(m.group(1)), title=m.group(2).strip(), page=page.number)
                outline.sections.append(section)
                continue

            if section is None:
                outline.preamble.append((page.number, line))
                continue

            m = _CLAUSE.match(line)
            if m:
                number = tuple(int(p) for p in m.group(1).split("."))
                if number == _expected_next(section, len(number)):
                    section.clauses.append(Clause(number=number, page=page.number, lines=[m.group(2).strip()]))
                    continue

            if section.clauses:
                section.clauses[-1].lines.append(line)
            else:  # text between a heading and its first clause
                section.clauses.append(Clause(number=(section.number, 0), page=page.number, lines=[line]))
    return outline


def _expected_next(section: Section, depth: int) -> tuple[int, ...] | None:
    """The only clause number that may legitimately come next at this depth."""
    if depth == 2:
        tops = [c.number for c in section.clauses if c.is_top]
        return (section.number, (tops[-1][1] if tops else 0) + 1)
    if depth == 3 and section.clauses:
        current_top = section.clauses[-1].number[:2]
        subs = [c.number for c in section.clauses if len(c.number) == 3 and c.number[:2] == current_top]
        return (*current_top, (subs[-1][2] if subs else 0) + 1)
    return None


# --- chunking -------------------------------------------------------------------

def _group_by_top_clause(section: Section) -> list[list[Clause]]:
    groups: list[list[Clause]] = []
    for c in section.clauses:
        if c.is_top or not groups:
            groups.append([c])
        else:
            groups[-1].append(c)
    return groups


def _label(section: Section, top: Clause, part: tuple[int, int] | None) -> str:
    num = str(section.number) if top.number[1] == 0 else top.label
    suffix = f" ({part[0]}/{part[1]})" if part else ""
    return f"§{num} {section.title}{suffix}"


def _pieces(group: list[Clause]) -> list[tuple[int, str]]:
    """Text units to pack: each clause as `number text`, long ones split by sentence."""
    out: list[tuple[int, str]] = []
    for c in group:
        text = c.text if c.number[1] == 0 else f"{c.label} {c.text}"
        if estimate_tokens(text) <= TARGET_TOKENS:
            out.append((c.page, text))
            continue
        buf = ""
        for sentence in _SENTENCE_END.split(text):
            if buf and estimate_tokens(f"{buf} {sentence}") > TARGET_TOKENS:
                out.append((c.page, buf))
                buf = sentence
            else:
                buf = f"{buf} {sentence}".strip()
        if buf:
            out.append((c.page, buf))
    return out


def _pack(pieces: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Greedy: consecutive pieces up to TARGET_TOKENS; page = first piece's page."""
    packed: list[tuple[int, str]] = []
    for page, text in pieces:
        if packed and estimate_tokens(f"{packed[-1][1]}\n{text}") <= TARGET_TOKENS:
            packed[-1] = (packed[-1][0], f"{packed[-1][1]}\n{text}")
        else:
            packed.append((page, text))
    return packed


def policy_chunks(parsed: ParsedDocument, entry: ManifestEntry) -> list[ChunkDraft]:
    outline = parse_outline(parsed)
    if not outline.sections:  # not numbered regulation text after all: one chunk per page
        return [ChunkDraft(content=p.text, page=p.number) for p in parsed.pages if p.text]

    drafts: list[ChunkDraft] = []
    if outline.preamble:
        drafts.append(
            ChunkDraft(
                content="\n".join(line for _, line in outline.preamble),
                page=outline.preamble[0][0],
                section="Preamble",
            )
        )
    for section in outline.sections:
        for group in _group_by_top_clause(section):
            parts = _pack(_pieces(group))
            for i, (page, text) in enumerate(parts, start=1):
                part = (i, len(parts)) if len(parts) > 1 else None
                drafts.append(
                    ChunkDraft(
                        content=f"{section.heading}\n{text}",
                        page=page,
                        section=_label(section, group[0], part),
                    )
                )
    return drafts


CHUNKERS["policy"] = policy_chunks
