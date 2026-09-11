"""Tools shared across all three roles (plan.md §6).

`search_university_policies` is a keyword-match placeholder: `doc_chunks` is only
populated by the Phase-3 RAG ingest, so it returns an empty list until then —
the tool shape (and its citation-friendly result fields) is already final.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from app.auth.context import AuthContext, Role
from app.ai.tools.registry import Scope, tool
from app.models import (
    AcademicCalendarEvent,
    Announcement,
    CourseOffering,
    DocChunk,
    Document,
    Enrollment,
    Faculty,
    Student,
)


def _caller_dept_code(db: Session, ctx: AuthContext) -> str | None:
    if ctx.role is Role.STUDENT:
        return db.get(Student, ctx.student_id).dept_code
    if ctx.role is Role.FACULTY:
        return db.get(Faculty, ctx.faculty_id).dept_code
    return None


def _caller_course_codes(db: Session, ctx: AuthContext) -> list[str]:
    if ctx.role is Role.STUDENT:
        stmt = (
            select(CourseOffering.subject_code)
            .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
            .where(Enrollment.student_id == ctx.student_id, Enrollment.term == ctx.term)
        )
    elif ctx.role is Role.FACULTY:
        stmt = select(CourseOffering.subject_code).where(
            CourseOffering.faculty_id == ctx.faculty_id, CourseOffering.term == ctx.term
        )
    else:
        return []
    return list(db.scalars(stmt.distinct()))


@tool(
    name="search_university_policies",
    description=(
        "Keyword search over ingested university policy documents for relevant passages. "
        "(Placeholder until the Phase-3 semantic RAG ingest lands.)"
    ),
    allowed_roles={Role.STUDENT, Role.FACULTY, Role.ADMIN},
    scope=Scope.UNIVERSITY,
)
def search_university_policies(*, ctx: AuthContext, db: Session, query: str, **_: Any) -> list[dict[str, Any]]:
    rows = db.execute(
        select(DocChunk.id, DocChunk.content, DocChunk.section, Document.title)
        .join(Document, Document.id == DocChunk.document_id)
        .where(DocChunk.content.ilike(f"%{query}%"))
        .limit(5)
    )
    return [
        {"chunk_id": r.id, "document": r.title, "section": r.section, "excerpt": r.content[:300]}
        for r in rows
    ]


@tool(
    name="get_academic_calendar",
    description="University academic calendar events (term dates, exams, holidays, registration windows), optionally filtered by event type.",
    allowed_roles={Role.STUDENT, Role.FACULTY, Role.ADMIN},
    scope=Scope.UNIVERSITY,
)
def get_academic_calendar(
    *, ctx: AuthContext, db: Session, event_type: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    q = select(AcademicCalendarEvent).where(
        or_(AcademicCalendarEvent.term == ctx.term, AcademicCalendarEvent.term.is_(None))
    )
    if event_type:
        q = q.where(AcademicCalendarEvent.event_type == event_type)
    q = q.order_by(AcademicCalendarEvent.start_date)
    return [
        {
            "event": r.event,
            "event_type": r.event_type,
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "applies_to": r.applies_to,
        }
        for r in db.scalars(q)
    ]


@tool(
    name="get_my_announcements",
    description="Announcements addressed to the caller: university-wide, their department, or courses they're enrolled in/teach.",
    allowed_roles={Role.STUDENT, Role.FACULTY, Role.ADMIN},
    scope=Scope.SELF,
)
def get_my_announcements(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    role_match = Announcement.audience_roles.ilike(f"%{ctx.role.value}%")
    if ctx.role is Role.ADMIN:
        # admins have no dept/course scope of their own; university-wide role match is enough
        conditions = [role_match]
    else:
        dept_code = _caller_dept_code(db, ctx)
        course_codes = _caller_course_codes(db, ctx)
        scope_clauses = [Announcement.scope == "university"]
        if dept_code:
            scope_clauses.append(and_(Announcement.scope == "department", Announcement.scope_ref == dept_code))
        if course_codes:
            scope_clauses.append(and_(Announcement.scope == "course", Announcement.scope_ref.in_(course_codes)))
        conditions = [role_match, or_(*scope_clauses)]

    rows = db.scalars(select(Announcement).where(*conditions).order_by(desc(Announcement.posted_at)).limit(20))
    return [
        {
            "title": r.title,
            "body": r.body,
            "scope": r.scope,
            "posted_at": r.posted_at.isoformat() if r.posted_at else None,
        }
        for r in rows
    ]
