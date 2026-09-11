"""Faculty OWN_COURSES read tools (plan.md §6).

Every course-level tool goes through `_faculty_offerings`: a faculty member only
ever sees offerings where `course_offerings.faculty_id` is *their own* id from
AuthContext. Asking about a course they don't teach yields nothing — not an
error, so the model can say "you don't teach that course" rather than guess.
Admins pass the same gate ungated (UNIVERSITY scope on the same tool).

`list_course_students` and `list_students_below_attendance` already live in
app.ai.tools.builtin; this module completes the group.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.ai.tools.builtin import PRESENT, _faculty_offerings
from app.ai.tools.registry import Scope, tool
from app.auth.context import AuthContext, Role
from app.models import (
    Assessment,
    AttendanceRecord,
    AttendanceSession,
    Classroom,
    CourseOffering,
    Enrollment,
    Mark,
    Student,
    Submission,
    TimetableSlot,
)

FACULTY_ROLES = {Role.FACULTY, Role.ADMIN}
ATTENDANCE_RISK_PCT = 75.0  # the university's own attendance floor
MARKS_RISK_PCT = 40.0  # below this share of max marks on graded work
ASSIGNMENT_PREFIX = "Assignment"  # assessments.type is "Assignment-1", "Assignment-2", ...


def _num(value: Any) -> float | None:
    return float(value) if value is not None else None


@tool(
    name="get_my_teaching_courses",
    description="Courses the calling faculty member teaches this term, with division, session type and enrolled count.",
    allowed_roles={Role.FACULTY},
    scope=Scope.OWN_COURSES,
)
def get_my_teaching_courses(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    enrolled = (
        select(func.count(Enrollment.id))
        .where(Enrollment.offering_id == CourseOffering.id, Enrollment.status == "enrolled")
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            CourseOffering.subject_code,
            CourseOffering.subject_name,
            CourseOffering.semester,
            CourseOffering.session_type,
            CourseOffering.division,
            CourseOffering.lab_group,
            enrolled.label("enrolled"),
        )
        .where(CourseOffering.faculty_id == ctx.faculty_id, CourseOffering.term == ctx.term)
        .order_by(CourseOffering.subject_code, CourseOffering.division, CourseOffering.lab_group)
    )
    return [
        {
            "course": r.subject_code,
            "name": r.subject_name,
            "semester": r.semester,
            "session_type": r.session_type,
            "division": r.division,
            "lab_group": r.lab_group,
            "enrolled": r.enrolled,
        }
        for r in rows
    ]


@tool(
    name="get_my_teaching_schedule",
    description="The calling faculty member's weekly teaching timetable, optionally filtered to one day (0=Mon..5=Sat).",
    allowed_roles={Role.FACULTY},
    scope=Scope.OWN_COURSES,
)
def get_my_teaching_schedule(
    *, ctx: AuthContext, db: Session, day: int | None = None, **_: Any
) -> list[dict[str, Any]]:
    q = (
        select(
            TimetableSlot.day_of_week,
            TimetableSlot.start_time,
            TimetableSlot.end_time,
            TimetableSlot.session_type,
            CourseOffering.subject_code,
            CourseOffering.subject_name,
            CourseOffering.division,
            Classroom.code.label("room"),
        )
        .join(CourseOffering, CourseOffering.id == TimetableSlot.offering_id)
        .outerjoin(Classroom, Classroom.id == TimetableSlot.classroom_id)
        .where(CourseOffering.faculty_id == ctx.faculty_id, CourseOffering.term == ctx.term)
    )
    if day is not None:
        q = q.where(TimetableSlot.day_of_week == day)
    q = q.order_by(TimetableSlot.day_of_week, TimetableSlot.start_time)
    return [
        {
            "day_of_week": r.day_of_week,
            "start_time": r.start_time.strftime("%H:%M"),
            "end_time": r.end_time.strftime("%H:%M"),
            "course": r.subject_code,
            "name": r.subject_name,
            "division": r.division,
            "session_type": r.session_type,
            "room": r.room,
        }
        for r in db.execute(q)
    ]


def _attendance_per_student(offerings: list[int]):
    """(student_id, attended, total) per student across the given offerings."""
    total = func.count(AttendanceRecord.id).label("total")
    attended = func.count(AttendanceRecord.id).filter(AttendanceRecord.status.in_(PRESENT)).label("attended")
    return (
        select(AttendanceRecord.student_id, attended, total)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(AttendanceSession.offering_id.in_(offerings))
        .group_by(AttendanceRecord.student_id)
        .subquery()
    )


@tool(
    name="get_course_attendance_summary",
    description="Attendance overview for a course you teach: sessions held, class average, and how many students are under 75%.",
    allowed_roles=FACULTY_ROLES,
    scope=Scope.OWN_COURSES,
)
def get_course_attendance_summary(
    *, ctx: AuthContext, db: Session, course_code: str, **_: Any
) -> dict[str, Any] | None:
    offerings = _faculty_offerings(db, ctx, course_code)
    if not offerings:
        return None
    sessions = db.scalar(
        select(func.count(AttendanceSession.id)).where(AttendanceSession.offering_id.in_(offerings))
    )
    per = _attendance_per_student(offerings)
    pct = per.c.attended * 100.0 / func.nullif(per.c.total, 0)
    row = db.execute(
        select(
            func.count(per.c.student_id).label("students"),
            func.avg(pct).label("average"),
            func.count(per.c.student_id).filter(pct < ATTENDANCE_RISK_PCT).label("below"),
            func.min(pct).label("lowest"),
        )
    ).one()
    return {
        "course": course_code,
        "sessions_held": sessions or 0,
        "students": row.students,
        "average_percent": round(float(row.average), 1) if row.average is not None else None,
        "below_75_percent": row.below,
        "lowest_percent": round(float(row.lowest), 1) if row.lowest is not None else None,
    }


@tool(
    name="list_missing_submissions",
    description="Students in a course you teach who have not submitted (or submitted late) an assignment; optionally one assignment by title or type.",
    allowed_roles=FACULTY_ROLES,
    scope=Scope.OWN_COURSES,
)
def list_missing_submissions(
    *, ctx: AuthContext, db: Session, course_code: str, assessment: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    offerings = _faculty_offerings(db, ctx, course_code)
    if not offerings:
        return []
    q = (
        select(
            Student.roll_no,
            Student.full_name,
            Assessment.type,
            Assessment.title,
            Assessment.due_date,
            Submission.status,
        )
        .join(Submission, Submission.student_id == Student.id)
        .join(Assessment, Assessment.id == Submission.assessment_id)
        .where(
            Assessment.offering_id.in_(offerings),
            Submission.status.in_(("missing", "late")),
        )
    )
    if assessment:
        q = q.where((Assessment.type == assessment) | (Assessment.title == assessment))
    q = q.order_by(Assessment.due_date, Submission.status, Student.roll_no)
    return [
        {
            "roll_no": r.roll_no,
            "full_name": r.full_name,
            "assessment": r.title or r.type,
            "type": r.type,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "status": r.status,
        }
        for r in db.execute(q)
    ]


@tool(
    name="get_course_marks_summary",
    description="Per-assessment marks statistics for a course you teach (graded count, mean, lowest, highest, absentees); optionally one assessment type.",
    allowed_roles=FACULTY_ROLES,
    scope=Scope.OWN_COURSES,
)
def get_course_marks_summary(
    *, ctx: AuthContext, db: Session, course_code: str, assessment_type: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    offerings = _faculty_offerings(db, ctx, course_code)
    if not offerings:
        return []
    scored = Mark.score.isnot(None) & (Mark.is_absent.is_(False))
    q = (
        select(
            Assessment.type,
            Assessment.title,
            Assessment.max_marks,
            func.count(Mark.id).filter(scored).label("graded"),
            func.avg(Mark.score).filter(scored).label("mean"),
            func.min(Mark.score).filter(scored).label("lowest"),
            func.max(Mark.score).filter(scored).label("highest"),
            func.count(Mark.id).filter(Mark.is_absent.is_(True)).label("absent"),
        )
        .join(Mark, Mark.assessment_id == Assessment.id)
        .where(Assessment.offering_id.in_(offerings))
        .group_by(Assessment.type, Assessment.title, Assessment.max_marks)
    )
    if assessment_type:
        q = q.where(Assessment.type == assessment_type)
    q = q.order_by(Assessment.type)
    return [
        {
            "assessment": r.title or r.type,
            "type": r.type,
            "max_marks": _num(r.max_marks),
            "graded": r.graded,
            "mean": round(float(r.mean), 1) if r.mean is not None else None,
            "lowest": _num(r.lowest),
            "highest": _num(r.highest),
            "absent": r.absent,
        }
        for r in db.execute(q)
    ]


@tool(
    name="identify_at_risk_students",
    description="Students in a course you teach flagged for low attendance (<75%), low marks (<40% on graded work) or missing assignments, with the reasons.",
    allowed_roles=FACULTY_ROLES,
    scope=Scope.OWN_COURSES,
)
def identify_at_risk_students(
    *, ctx: AuthContext, db: Session, course_code: str, **_: Any
) -> list[dict[str, Any]]:
    offerings = _faculty_offerings(db, ctx, course_code)
    if not offerings:
        return []

    att = _attendance_per_student(offerings)

    scored = Mark.score.isnot(None) & (Mark.is_absent.is_(False))
    marks = (
        select(
            Mark.student_id,
            (func.sum(Mark.score).filter(scored) * 100.0 / func.nullif(func.sum(Assessment.max_marks).filter(scored), 0)).label("pct"),
        )
        .join(Assessment, Assessment.id == Mark.assessment_id)
        .where(Assessment.offering_id.in_(offerings))
        .group_by(Mark.student_id)
        .subquery()
    )

    missing = (
        select(Submission.student_id, func.count(Submission.id).label("n"))
        .join(Assessment, Assessment.id == Submission.assessment_id)
        .where(Assessment.offering_id.in_(offerings), Submission.status == "missing")
        .group_by(Submission.student_id)
        .subquery()
    )

    att_pct = att.c.attended * 100.0 / func.nullif(att.c.total, 0)
    rows = db.execute(
        select(
            Student.roll_no,
            Student.full_name,
            att_pct.label("attendance"),
            marks.c.pct.label("marks"),
            func.coalesce(missing.c.n, 0).label("missing"),
        )
        .join(Enrollment, Enrollment.student_id == Student.id)
        .outerjoin(att, att.c.student_id == Student.id)
        .outerjoin(marks, marks.c.student_id == Student.id)
        .outerjoin(missing, missing.c.student_id == Student.id)
        .where(Enrollment.offering_id.in_(offerings), Enrollment.status == "enrolled")
        .order_by(Student.roll_no)
    )

    out: list[dict[str, Any]] = []
    for r in rows:
        reasons: list[str] = []
        attendance = round(float(r.attendance), 1) if r.attendance is not None else None
        marks_pct = round(float(r.marks), 1) if r.marks is not None else None
        if attendance is not None and attendance < ATTENDANCE_RISK_PCT:
            reasons.append(f"attendance {attendance}%")
        if marks_pct is not None and marks_pct < MARKS_RISK_PCT:
            reasons.append(f"marks {marks_pct}%")
        if r.missing:
            reasons.append(f"{r.missing} missing submission{'s' if r.missing > 1 else ''}")
        if reasons:
            out.append(
                {
                    "roll_no": r.roll_no,
                    "full_name": r.full_name,
                    "attendance_percent": attendance,
                    "marks_percent": marks_pct,
                    "missing_submissions": int(r.missing),
                    "reasons": "; ".join(reasons),
                }
            )
    # worst first: most reasons, then lowest attendance
    out.sort(key=lambda s: (-s["reasons"].count(";"), s["attendance_percent"] or 0))
    return out
