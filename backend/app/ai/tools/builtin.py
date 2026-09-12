"""A small set of real RBAC-guarded tools.

Enough to exercise every enforcement layer and to back GET /api/me. The full
catalog (plan.md §6) is Phase 2.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.context import AuthContext, Role
from app.ai.tools.registry import Scope, tool
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    CourseOffering,
    Enrollment,
    Faculty,
    Student,
)

PRESENT = ("present", "excused_leave")


@tool(
    name="get_my_profile",
    description="The caller's own profile (name, roll/employee no, department, standing).",
    allowed_roles={Role.STUDENT, Role.FACULTY},
    scope=Scope.SELF,
)
def get_my_profile(*, ctx: AuthContext, db: Session, **_: Any) -> dict[str, Any]:
    if ctx.role is Role.STUDENT:
        s = db.get(Student, ctx.student_id)
        return {
            "role": "student",
            "roll_no": s.roll_no,
            "full_name": s.full_name,
            "dept_code": s.dept_code,
            "semester": s.semester,
            "division": s.division,
            "cgpa": float(s.cgpa) if s.cgpa is not None else None,
        }
    f = db.get(Faculty, ctx.faculty_id)
    return {
        "role": "faculty",
        "employee_id": f.employee_id,
        "full_name": f.full_name,
        "dept_code": f.dept_code,
        "designation": f.designation,
        "is_hod": bool(f.is_hod),
    }


@tool(
    name="get_my_attendance",
    description="The calling student's attendance percentage per enrolled course this term.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_attendance(*, ctx: AuthContext, db: Session, course: str | None = None, **_: Any) -> list[dict[str, Any]]:
    q = (
        select(
            CourseOffering.subject_code,
            CourseOffering.subject_name,
            func.count(AttendanceRecord.id).label("total"),
            func.count(AttendanceRecord.id)
            .filter(AttendanceRecord.status.in_(PRESENT))
            .label("attended"),
        )
        .join(AttendanceSession, AttendanceSession.offering_id == CourseOffering.id)
        .join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.id)
        .where(
            AttendanceRecord.student_id == ctx.student_id,  # identity from context, never args
            CourseOffering.term == ctx.term,
        )
        .group_by(CourseOffering.subject_code, CourseOffering.subject_name)
    )
    if course:
        q = q.where(CourseOffering.subject_code == course)

    out = []
    for row in db.execute(q):
        pct = round(row.attended / row.total * 100, 1) if row.total else 0.0
        out.append(
            {
                "course": row.subject_code,
                "name": row.subject_name,
                "attended": row.attended,
                "total": row.total,
                "percent": pct,
            }
        )
    return out


def _faculty_offerings(db: Session, ctx: AuthContext, course_code: str | None) -> list[int]:
    """Offering ids for `course_code` that THIS faculty teaches (OWN_COURSES gate).

    Without a course code a faculty member gets every offering they teach this
    term — "which of my students…" needs no course named — and an admin
    (UNIVERSITY scope) gets every offering in the term: "which students are
    below 65% in IT?" is a question an admin does ask (eval a11).
    """
    stmt = select(CourseOffering.id).where(CourseOffering.term == ctx.term)
    if course_code:
        stmt = stmt.where(CourseOffering.subject_code == course_code.strip().upper())
    if ctx.role is Role.FACULTY:
        stmt = stmt.where(CourseOffering.faculty_id == ctx.faculty_id)
    return list(db.scalars(stmt))


@tool(
    name="list_course_students",
    description="Roster of students enrolled in a course you teach (omit course_code for all your courses).",
    allowed_roles={Role.FACULTY, Role.ADMIN},
    scope=Scope.OWN_COURSES,
)
def list_course_students(*, ctx: AuthContext, db: Session, course_code: str | None = None, **_: Any) -> list[dict[str, Any]]:
    offerings = _faculty_offerings(db, ctx, course_code)
    if not offerings:
        return []
    rows = db.execute(
        select(Student.roll_no, Student.full_name, Student.division)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.offering_id.in_(offerings))
        .order_by(Student.roll_no)
    )
    return [{"roll_no": r.roll_no, "full_name": r.full_name, "division": r.division} for r in rows]


@tool(
    name="list_students_below_attendance",
    description="Students whose attendance is below a threshold (default 75%) in a course you teach; omit course_code for all your courses (an admin: every course, optionally one dept).",
    allowed_roles={Role.FACULTY, Role.ADMIN},
    scope=Scope.OWN_COURSES,
)
def list_students_below_attendance(
    *, ctx: AuthContext, db: Session, course_code: str | None = None, threshold: float = 75.0,
    dept: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    offerings = _faculty_offerings(db, ctx, course_code)
    if not offerings:
        return []
    total = func.count(AttendanceRecord.id)
    attended = func.count(AttendanceRecord.id).filter(AttendanceRecord.status.in_(PRESENT))
    pct = (attended * 100.0 / func.nullif(total, 0)).label("pct")
    rows = db.execute(
        # per (student, course): Part IV §4.1 - attendance is assessed separately for every course,
        # so a student can be short in DBMS while fine overall
        select(Student.roll_no, Student.full_name, Student.dept_code, CourseOffering.subject_code, pct)
        .join(AttendanceRecord, AttendanceRecord.student_id == Student.id)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(CourseOffering, CourseOffering.id == AttendanceSession.offering_id)
        .where(AttendanceSession.offering_id.in_(offerings))
        .where(Student.dept_code == dept.strip().upper() if dept else True)
        .group_by(Student.id, Student.roll_no, Student.full_name, Student.dept_code, CourseOffering.subject_code)
        .having(attended * 100.0 / func.nullif(total, 0) < threshold)
        .order_by(pct, Student.roll_no)
    )
    return [
        {"roll_no": r.roll_no, "full_name": r.full_name, "dept": r.dept_code, "course": r.subject_code,
         "percent": round(float(r.pct), 1)}
        for r in rows
    ]
