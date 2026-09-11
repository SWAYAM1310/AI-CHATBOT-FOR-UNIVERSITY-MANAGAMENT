"""Structure-first chunker for `curriculum` documents (plan.md §8 "curriculum").

A syllabus is not prose: it is one repeating record per course, all on the
same university template. With position-sorted extraction (parsers.py) a
record reads:

    24MA101T Mathematics – I               <- code + title (title may wrap; the code
                                               token can sit on either line, or be a
                                               placeholder: 24ICxxxT, <Course Code>)
    Teaching Scheme Examination Scheme     <- the anchor every record has
    L T P C Hrs./Week Total Marks / MS ES IA LW LE/Viva
    3 1 0 4 4 25 50 25 -- -- 100           <- the values row: L T P C first
    COURSE OBJECTIVES  ...
    UNIT I: TITLE 08 Hrs.  /  body         (labs: LIST OF EXPERIMENT(S))
    TOTAL HOURS: 42 Hrs.
    COURSE OUTCOMES  CO1 : ...  (or a plain 1. 2. 3. list)
    TEXT/REFERENCE BOOKS  1. ...  2. ...

`parse_courses()` segments the line stream on the anchors into
`CourseRecord`s (with the page each starts on); `curriculum_chunks()` turns
each record into one *parent* chunk (code, title, credits, objectives, unit
titles) and *child* chunks (one per unit, one for the outcomes, one for the
books), each child carrying the course label so it reads on its own. Ingest
embeds parent + children together, late-chunked per course: a unit's vector
knows which course it belongs to and nothing else (§8).

Programme-structure tables (before the first record, and between semesters
in some PDFs) also contain "Teaching Scheme" as a column header; an anchor
with no course sections before the next anchor is not a record. Structure
lines are kept as plain "Programme structure" page chunks, never as part of
the course above them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.rag.chunkers.base import CHUNKERS, EXTRACTORS, ChunkDraft
from app.ai.rag.manifest import ManifestEntry
from app.ai.rag.parsers import ParsedDocument
from app.models import CourseOutcome, Curriculum, Document, Subject, SyllabusCourse, SyllabusUnit, Textbook

STRUCTURE_SECTION = "Programme structure"  # preface page chunks; the curriculum search tool skips these

_CODE_TOKEN = re.compile(r"(?<![\w-])(\d{2}[A-Z]{2,4}(?:\d{3}|[xX]{3}|\*{3})[A-Z]?)(?![\w-])")
_CODE_PLACEHOLDER = re.compile(r"<\s*course\s*code\s*>", re.I)
_ANCHOR = re.compile(r"^teaching\s+scheme\b", re.I)
_OBJECTIVES = re.compile(r"^course\s+objectives?\b", re.I)
_UNIT = re.compile(r"^unit\s*[-–]?\s*([IVX]+|\d+)\s*[:\-–.]?\s*(.*)$", re.I)
_EXPERIMENTS = re.compile(
    r"^((sr\.?\s+)?list\s+of\s+(experiments?|exercises?)|lab(oratory)?\s+experiments?"
    r"|details\s+of\s+laboratory\s+practicals?)\s*:?$",
    re.I,
)
_TOTAL_HOURS = re.compile(r"^total\s+hours?\b", re.I)
_OUTCOMES = re.compile(r"^course\s+outcomes?\b", re.I)
_BOOKS = re.compile(r"^(text|reference)[\w\s\-/&]{0,40}books?\s*:?$", re.I)
_HOURS_LINE = re.compile(r"^(\d+)\s*hrs?\.?$", re.I)
_HOURS_TAIL = re.compile(r"\s+(\d+)\s*hrs?\.?$", re.I)
_VALUES_ROW = re.compile(r"^(\d+(?:\.\d+)?|-+)(\s+(\d+(?:\.\d+)?|-+)){3,}$")
_CO = re.compile(r"\bCO\s*[-–]?\s*(\d+)\s*:?\s*")
_NUMBERED_ITEM = re.compile(r"(?:^|\s)(\d{1,2})\.\s+")
_LEAD_IN = re.compile(r"^.*?\bable\s+to\s*:?\s*", re.I)
_NUMBERED = re.compile(r"^\d+\.\s*")
_BULLET = re.compile(r"^[•Ø‣▪–\-\d.)-]+\s*")  # incl. Symbol-font private-use bullets
_WRAP_END = re.compile(r"[,(/&\-–]$|\b(and|for|of|in|to)$", re.I)
_PAGE_FURNITURE = re.compile(
    r"^(pandit\s+deendayal\s+energy\s+university\b.*|school\s+of\s+technology"
    r"|b\.?\s*tech\.?\s.*engineering[,.]?|department\s+of\s+.*engineering|ug\s+curriculum\s*\(.*\)"
    r"|semester\s*[–-]?\s*([IVX]+|\d+)|academic\s+year\s*:.*)$",
    re.I,
)
# a programme-structure table between two course records: ends the record above it
_STRUCTURE_HEAD = re.compile(
    r"^(course\s+structure\b|category\s+course$|(category\s+)?(semester\s+)?course\s+name\s+theory\b"
    r"|sr\.?\s*no\.?\s+(course\s+)?code\b)",
    re.I,
)
_TITLE_LOOKBACK = 3  # lines above the anchor that may hold code + title

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


@dataclass
class Unit:
    number: int
    title: str
    hours: int | None
    body: str
    page: int
    draft: int | None = None  # index of this unit's chunk, set by build()


@dataclass
class CourseRecord:
    code: str | None
    title: str
    page: int
    lecture: int | None = None
    tutorial: int | None = None
    practical: int | None = None
    credits: float | None = None
    objectives: list[str] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    outcomes: list[tuple[int, str]] = field(default_factory=list)
    books: list[str] = field(default_factory=list)
    outcomes_page: int | None = None
    books_page: int | None = None
    trailing: list[Line] = field(default_factory=list)  # structure-table lines after the record, if any
    draft: int | None = None  # index of the parent chunk, set by build()
    outcomes_draft: int | None = None
    books_draft: int | None = None

    @property
    def label(self) -> str:
        return f"{self.code} {self.title}" if self.code else self.title

    @property
    def scheme(self) -> str | None:
        if self.credits is None:
            return None
        ltp = "-".join("?" if v is None else str(v) for v in (self.lecture, self.tutorial, self.practical))
        return f"L-T-P {ltp}, {self.credits:g} credits"

    @property
    def has_sections(self) -> bool:
        return bool(self.objectives or self.units or self.outcomes or self.books)


Line = tuple[int, str]  # (page, text)


def _lines(parsed: ParsedDocument) -> list[Line]:
    out: list[Line] = []
    for page in parsed.pages:
        for raw in page.text.split("\n"):
            line = raw.strip()
            if line and not _PAGE_FURNITURE.match(line):
                out.append((page.number, line))
    return out


def _code_in(line: str) -> str | None:
    """The course code token in a header line: a real code, or "" for a placeholder."""
    m = _CODE_TOKEN.search(line)
    if m:
        return "" if "xxx" in m.group(1).lower() or "***" in m.group(1) else m.group(1)
    return "" if _CODE_PLACEHOLDER.search(line) else None


_TITLE_JUNK = re.compile(
    r"^(course\s*code\s*:?\s*[xX*]*\s*|[xX]{4,}\s+|\d(st|nd|rd|th)\s+semester\s+|UG_\S+\s+)+", re.I
)  # "Course Code: XXXX Machine Learning", "XXXXXX IC Technology", "2nd Semester UG_2_T(CE/ICT) Programming"


def _strip_code(line: str) -> str:
    line = _CODE_PLACEHOLDER.sub("", _CODE_TOKEN.sub("", line))
    return _TITLE_JUNK.sub("", line).strip(" <>*")  # "< Title >" is a template placeholder


def _wrapped(prev: str, cur: str) -> bool:
    """Do `prev` + `cur` read as one title split over two lines?"""
    if _NUMBERED.match(prev) or _NUMBERED.match(cur) or _section_start(prev) or _HOURS_LINE.match(prev):
        return False
    return bool(_WRAP_END.search(prev)) or cur[:1].islower() or cur.startswith(")") or (
        cur.count(")") > cur.count("(")
    )


def _head_start(lines: list[Line], anchor: int, floor: int) -> int:
    """Index of the first header line of the record whose anchor is at `anchor`."""
    lo = max(floor, anchor - _TITLE_LOOKBACK)
    code_at = next((j for j in range(anchor - 1, lo - 1, -1) if _code_in(lines[j][1]) is not None), None)
    start = code_at if code_at is not None else anchor - 1
    title = _strip_code(lines[start][1])
    if not title and start - 1 >= lo and not _NUMBERED.match(lines[start - 1][1]):
        start -= 1  # the code sat on its own line; the title is the line above it
        title = _strip_code(lines[start][1])
    while start - 1 >= lo and _wrapped(lines[start - 1][1], title):
        start -= 1
        title = f"{_strip_code(lines[start][1])} {title}".strip()
    return max(start, floor)


def parse_courses(parsed: ParsedDocument) -> tuple[list[Line], list[CourseRecord]]:
    """(lines before the first record, one CourseRecord per genuine 'Teaching Scheme' anchor)."""
    lines = _lines(parsed)
    anchors = [i for i, (_, t) in enumerate(lines) if _ANCHOR.match(t) and i > 0]
    starts: list[int] = []
    for i, anchor in enumerate(anchors):
        until = anchors[i + 1] if i + 1 < len(anchors) else len(lines)
        if not any(_section_start(t) for _, t in lines[anchor:until]):
            continue  # a structure table's column header, not a course
        starts.append(_head_start(lines, anchor, starts[-1] + 1 if starts else 0))
    records = [_parse_record(lines[s:e]) for s, e in zip(starts, [*starts[1:], len(lines)])]
    structure = lines[: starts[0]] if starts else lines
    for rec in records:
        structure.extend(rec.trailing)
    return structure, records


def _parse_record(lines: list[Line]) -> CourseRecord:
    anchor = next(k for k, (_, t) in enumerate(lines) if _ANCHOR.match(t))
    head = [t for _, t in lines[:anchor]]
    code = next((c for c in (_code_in(t) for t in head) if c), None)
    title = " ".join(_strip_code(t) for t in head).strip() or "(untitled course)"
    rec = CourseRecord(code=code, title=re.sub(r"\s+", " ", title), page=lines[0][0])

    # teaching scheme: the first values row after the anchor; L T P C lead it
    i = anchor + 1
    while i < len(lines) and not _section_start(lines[i][1]):
        m = _VALUES_ROW.match(lines[i][1])
        if m:
            vals = lines[i][1].split()
            rec.lecture, rec.tutorial, rec.practical = (_int(v) for v in vals[:3])
            rec.credits = _float(vals[3])
            i += 1
            break
        i += 1

    state: str | None = None
    unit: Unit | None = None
    buf: list[Line] = []

    def close() -> None:
        nonlocal unit
        if state == "units" and unit is not None:
            unit.body = _join(buf)
            rec.units.append(unit)
        elif state == "outcomes":
            rec.outcomes = _parse_outcomes(buf)
        elif state == "books":
            rec.books = _parse_books(buf)
        unit = None

    for k, (page, t) in enumerate(lines[i:], start=i):
        if _STRUCTURE_HEAD.match(t):
            rec.trailing = lines[k:]  # a structure table follows; it is not part of this course
            break
        if _section_start(t):
            close()
            buf = []
            if _OBJECTIVES.match(t):
                state = "objectives"
            elif _OUTCOMES.match(t):
                state, rec.outcomes_page = "outcomes", page
            elif _BOOKS.match(t):
                state, rec.books_page = "books", page
            elif _TOTAL_HOURS.match(t):
                state = None
            else:
                state = "units"
                unit = _open_unit(t, page, len(rec.units) + 1)
            continue
        if state == "units" and unit is not None and not buf:
            h = _HOURS_LINE.match(t)
            if h:
                unit.hours = int(h.group(1))
                continue
            if not unit.title and not _NUMBERED.match(t):
                unit.title, unit.hours = _split_hours(t)
                continue
        if state == "objectives":
            rec.objectives.append(t)
        elif state in ("units", "outcomes", "books"):
            buf.append((page, t))
    close()
    rec.objectives = _clean_objectives(rec.objectives)
    return rec


def _open_unit(t: str, page: int, ordinal: int) -> Unit:
    m = _UNIT.match(t)
    if not m:
        return Unit(number=ordinal, title="List of experiments", hours=None, body="", page=page)
    title, hours = _split_hours(m.group(2).strip())
    return Unit(number=_unit_number(m.group(1)), title=title, hours=hours, body="", page=page)


def _split_hours(t: str) -> tuple[str, int | None]:
    m = _HOURS_TAIL.search(t)
    return (t[: m.start()].strip(), int(m.group(1))) if m else (t.strip(" :-–"), None)


def _section_start(t: str) -> bool:
    return bool(
        _OBJECTIVES.match(t) or _UNIT.match(t) or _EXPERIMENTS.match(t)
        or _TOTAL_HOURS.match(t) or _OUTCOMES.match(t) or _BOOKS.match(t)
    )


def _unit_number(token: str) -> int:
    token = token.upper()
    return ROMAN.get(token) or int(token)


def _int(v: str) -> int | None:
    try:
        return int(float(v))
    except ValueError:
        return None


def _float(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def _join(buf: list[Line]) -> str:
    return " ".join(t for _, t in buf).strip()


def _clean_objectives(items: list[str]) -> list[str]:
    """Bullets come out as their own lines; wrapped continuations are glued back."""
    out: list[str] = []
    for t in items:
        t = _BULLET.sub("", t).strip()
        if not t:
            continue
        if out and out[-1][-1] not in ".;:" and t[0].islower():
            out[-1] = f"{out[-1]} {t}"
        else:
            out.append(t)
    return out


def _parse_outcomes(buf: list[Line]) -> list[tuple[int, str]]:
    """`CO1 : text` labels, or a plain numbered list when the template dropped the labels."""
    text = _join(buf)
    parts = _CO.split(text)  # ['On completion...', '1', 'Identify ...', '2', ...]
    if len(parts) < 3:
        parts = _NUMBERED_ITEM.split(_LEAD_IN.sub("", text, count=1))
    out: list[tuple[int, str]] = []
    for n, body in zip(parts[1::2], parts[2::2]):
        body = body.strip().lstrip(":-– ").strip()
        if body:
            out.append((int(n), body))
    return out


def _parse_books(buf: list[Line]) -> list[str]:
    out: list[str] = []
    for _, t in buf:
        if _NUMBERED.match(t) or not out:
            out.append(_NUMBERED.sub("", t).strip())
        else:
            out[-1] = f"{out[-1]} {t}".strip()
    return [b for b in out if b]


# --- chunks -----------------------------------------------------------------

def parent_text(rec: CourseRecord) -> str:
    parts = [rec.label]
    if rec.scheme:
        parts.append(rec.scheme)
    if rec.objectives:
        parts.append("Course objectives:")
        parts.extend(f"- {o}" for o in rec.objectives)
    if rec.units:
        parts.append("Units: " + "; ".join(f"{u.number}. {u.title}" for u in rec.units if u.title))
    return "\n".join(parts)


def build(parsed: ParsedDocument, entry: ManifestEntry) -> tuple[list[ChunkDraft], list[CourseRecord]]:
    """Drafts for the document plus the records behind them, each annotated with its draft indices."""
    preface, records = parse_courses(parsed)
    drafts: list[ChunkDraft] = []

    by_page: dict[int, list[str]] = {}
    for page, t in preface:
        by_page.setdefault(page, []).append(t)
    for page, texts in by_page.items():
        drafts.append(ChunkDraft(content="\n".join(texts), page=page, section=STRUCTURE_SECTION))

    for rec in records:
        rec.draft = len(drafts)
        drafts.append(ChunkDraft(content=parent_text(rec), page=rec.page, section=rec.label))
        for u in rec.units:
            head = f"{rec.label} / Unit {u.number}: {u.title}".rstrip(": ")
            hours = f" ({u.hours} hrs)" if u.hours else ""
            u.draft = len(drafts)
            drafts.append(ChunkDraft(content=f"{head}{hours}\n{u.body}".strip(), page=u.page, section=head, parent=rec.draft))
        if rec.outcomes:
            body = "\n".join(f"CO{n}: {t}" for n, t in rec.outcomes)
            rec.outcomes_draft = len(drafts)
            drafts.append(
                ChunkDraft(content=f"{rec.label} / Course outcomes\n{body}", page=rec.outcomes_page or rec.page,
                           section=f"{rec.label} / Course outcomes", parent=rec.draft)
            )
        if rec.books:
            body = "\n".join(f"{i}. {b}" for i, b in enumerate(rec.books, 1))
            rec.books_draft = len(drafts)
            drafts.append(
                ChunkDraft(content=f"{rec.label} / Text and reference books\n{body}", page=rec.books_page or rec.page,
                           section=f"{rec.label} / Books", parent=rec.draft)
            )
    return drafts, records


def curriculum_chunks(parsed: ParsedDocument, entry: ManifestEntry) -> list[ChunkDraft]:
    return build(parsed, entry)[0]


# --- relational extract -----------------------------------------------------

_PAREN = re.compile(r"\(.*?\)")  # "(For CS, ICT)" audience qualifiers
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def title_key(title: str) -> str:
    """Normalised title for matching a syllabus record to a `subjects` row by name."""
    key = _NON_ALNUM.sub(" ", _PAREN.sub(" ", title.lower()))
    key = " ".join(key.split())
    key = re.sub(r"\blab\b", "laboratory", key)
    key = re.sub(r"\b(ii|2)$", "2", key)  # "– II" / "-2" suffixes name the same course
    key = re.sub(r"\b(i|1)$", "1", key)
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in key.split())


def extract_courses(db: Session, document: Document, parsed: ParsedDocument, entry: ManifestEntry, rows: list) -> int:
    """Write syllabus_courses / syllabus_units / course_outcomes / textbooks for one document.

    `rows` are the freshly written chunk rows, index-aligned with the drafts
    `build()` produced, so every row can cite the chunk it came from. Runs in
    the ingest transaction; `_drop_chunks` removed the previous extract.
    """
    _, records = build(parsed, entry)
    by_name = _subject_codes_by_name(db)
    dept_subjects = set(db.scalars(select(Curriculum.subject_code).where(Curriculum.dept_code == entry.dept_code)))
    for rec in records:
        subject_code = _link_subject(db, rec, by_name, dept_subjects)
        course = SyllabusCourse(
            document_id=document.id,
            dept_code=entry.dept_code,
            code=rec.code,
            subject_code=subject_code,
            title=rec.title,
            title_key=title_key(rec.title),
            lecture_hours=rec.lecture,
            tutorial_hours=rec.tutorial,
            practical_hours=rec.practical,
            credits=rec.credits,
            objectives=rec.objectives or None,
            page=rec.page,
            source_chunk_id=rows[rec.draft].id if rec.draft is not None else None,
        )
        db.add(course)
        db.flush()
        db.add_all(
            SyllabusUnit(
                course_id=course.id, number=u.number, title=u.title or None, hours=u.hours, topics=u.body or None,
                page=u.page, source_chunk_id=rows[u.draft].id if u.draft is not None else None,
            )
            for u in rec.units
        )
        co_chunk = rows[rec.outcomes_draft].id if rec.outcomes_draft is not None else None
        db.add_all(CourseOutcome(course_id=course.id, number=n, text=t, source_chunk_id=co_chunk) for n, t in rec.outcomes)
        book_chunk = rows[rec.books_draft].id if rec.books_draft is not None else None
        db.add_all(
            Textbook(course_id=course.id, position=i, citation=b, source_chunk_id=book_chunk)
            for i, b in enumerate(rec.books, 1)
        )
    db.flush()
    return len(records)


def _link_subject(db: Session, rec: CourseRecord, by_name: dict[str, list[str]], dept_subjects: set[str]) -> str | None:
    """The `subjects` row this record describes, or None.

    Name first: the generated dataset reused the PDFs' names but not their codes,
    so a code that exists in `subjects` can name a different course (the PDF's
    24CS202T is DBMS; the dataset's is Digital Logic). When several subjects
    share a name (DBMS is taught to CP and EC under different codes) the one in
    this department's `curriculum` wins. The printed code is trusted only when
    the two names largely agree.
    """
    key = title_key(rec.title)
    candidates = by_name.get(key, [])
    if candidates:
        return next((c for c in candidates if c in dept_subjects), candidates[0])
    if rec.code:
        subject = db.get(Subject, rec.code)
        if subject is not None and _similar(key, title_key(subject.subject_name)):
            return rec.code
    return None


def _similar(a: str, b: str) -> bool:
    """Do two title keys share most of their words?"""
    wa, wb = set(a.split()), set(b.split())
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.6


def _subject_codes_by_name(db: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for code, name in db.execute(select(Subject.subject_code, Subject.subject_name).order_by(Subject.subject_code)):
        out.setdefault(title_key(name), []).append(code)
    return out


CHUNKERS["curriculum"] = curriculum_chunks
EXTRACTORS["curriculum"] = extract_courses
