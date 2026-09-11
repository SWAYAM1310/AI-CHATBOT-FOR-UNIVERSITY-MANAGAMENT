"""Curriculum tools, shared by every role (plan.md §8 "curriculum").

Two ways in, by design:

- `get_course_syllabus` is an **exact lookup** over the relational extract
  (`syllabus_courses` and its children): credits, scheme, units, outcomes,
  textbooks. "How many credits is DBMS?" must never be answered by
  similarity search.
- `search_curriculum` is **retrieval** over the curriculum chunks for the
  genuinely fuzzy question — "which course teaches normalisation?" — with the
  parent course record hydrated so a unit is never seen out of context.

Neither is role-scoped: the syllabus is public within the university. The
caller's department only breaks ties when several departments teach a course
of the same name.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.rag.chunkers.curriculum import STRUCTURE_SECTION, title_key
from app.ai.rag.retriever import retrieve
from app.ai.tools.registry import Scope, tool
from app.ai.tools.shared_tools import _caller_dept_code
from app.auth.context import AuthContext, Role
from app.models import CourseOutcome, Document, SyllabusCourse, SyllabusUnit, Textbook

CURRICULUM_HITS = 5
MAX_MATCHES = 8  # candidates listed back when a name is ambiguous


@tool(
    name="get_course_syllabus",
    description=(
        "Exact syllabus of one course by code or name: credits and L-T-P scheme, objectives, "
        "units with topics and hours, course outcomes and textbooks. Pass unit to get one unit's topics."
    ),
    allowed_roles={Role.STUDENT, Role.FACULTY, Role.ADMIN},
    scope=Scope.UNIVERSITY,
)
def get_course_syllabus(
    *, ctx: AuthContext, db: Session, course: str, unit: int | None = None, **_: Any
) -> dict[str, Any]:
    matches = _find_courses(db, course.strip(), _caller_dept_code(db, ctx))
    if not matches:
        return {"error": f"no course matching '{course}' in the syllabus documents"}
    if len({(m.title_key) for m in matches}) > 1:
        return {
            "matches": [f"{m.code or '(no code)'} {m.title} [{m.dept_code}]" for m in matches[:MAX_MATCHES]],
            "hint": "several courses match; ask for one by code or full name",
        }

    c = matches[0]
    doc_title = db.scalar(select(Document.title).where(Document.id == c.document_id))
    units = db.scalars(select(SyllabusUnit).where(SyllabusUnit.course_id == c.id).order_by(SyllabusUnit.number)).all()
    out: dict[str, Any] = {
        "course": f"{c.code or ''} {c.title}".strip(),
        "department": c.dept_code,
        "subject_code": c.subject_code,
        "credits": float(c.credits) if c.credits is not None else None,
        "scheme": f"L-T-P {c.lecture_hours}-{c.tutorial_hours}-{c.practical_hours}" if c.credits is not None else None,
        "source": f"{doc_title}, p.{c.page}",
        "chunk_id": c.source_chunk_id,
    }
    if unit is not None:
        u = next((x for x in units if x.number == unit), None)
        if u is None:
            out["error"] = f"no unit {unit}; the course has units {[x.number for x in units]}"
            return out
        out["unit"] = _unit_line(u)
        return out

    out["objectives"] = " ".join(f"{i}) {o}" for i, o in enumerate(c.objectives or [], 1)) or None
    out["units"] = " || ".join(_unit_line(u) for u in units) or None
    outcomes = db.scalars(
        select(CourseOutcome).where(CourseOutcome.course_id == c.id).order_by(CourseOutcome.number)
    ).all()
    out["outcomes"] = "; ".join(f"CO{o.number}: {o.text}" for o in outcomes) or None
    books = db.scalars(select(Textbook).where(Textbook.course_id == c.id).order_by(Textbook.position)).all()
    out["textbooks"] = "; ".join(f"{b.position}. {b.citation}" for b in books) or None
    return out


def _unit_line(u: SyllabusUnit) -> str:
    hours = f" ({u.hours} hrs)" if u.hours else ""
    return f"Unit {u.number}: {u.title or ''}{hours}: {u.topics or ''}".replace(":  ", ": ").strip(": ")


def _find_courses(db: Session, course: str, dept: str | None) -> list[SyllabusCourse]:
    """Rows for a code or a name; the caller's department first when it teaches the course too."""
    code = course.upper()
    # the dataset's code is the one the caller sees on their own records (timetable, marks);
    # the code printed in the PDF can collide with it and name a different course
    rows = db.scalars(select(SyllabusCourse).where(SyllabusCourse.subject_code == code)).all()
    if not rows:
        rows = db.scalars(select(SyllabusCourse).where(SyllabusCourse.code == code)).all()
    if not rows:
        key = title_key(course)
        rows = db.scalars(select(SyllabusCourse).where(SyllabusCourse.title_key == key)).all()
    if not rows and len(course) >= 3:
        rows = db.scalars(
            select(SyllabusCourse).where(func.lower(SyllabusCourse.title).contains(course.lower())).limit(50)
        ).all()
    if dept and any(r.dept_code == dept for r in rows):
        rows = [r for r in rows if r.dept_code == dept] + [r for r in rows if r.dept_code != dept]
    return rows


@tool(
    name="search_curriculum",
    description=(
        "Search the syllabus documents for topics, units, outcomes or textbooks when the course is not "
        "known (e.g. which course covers normalisation). Returns passages with their course."
    ),
    allowed_roles={Role.STUDENT, Role.FACULTY, Role.ADMIN},
    scope=Scope.UNIVERSITY,
)
def search_curriculum(*, ctx: AuthContext, db: Session, query: str, **_: Any) -> list[dict[str, Any]]:
    hits = retrieve(
        db, query, role=ctx.role.value, k=CURRICULUM_HITS, doc_types=("curriculum",),
        exclude_sections=(STRUCTURE_SECTION,),
    )
    return [h.as_passage() for h in hits]
