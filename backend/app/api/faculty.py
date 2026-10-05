"""Faculty portal: the website's own view of what a faculty member teaches.

Every route is faculty-only and keyed by an `offering_id` / `assessment_id`
that is re-checked against the caller's own `faculty_id` — a section the caller
does not teach is a 404, never a 403, so ids cannot be probed. Writes call the
chat's action tools (see `app.api.toolcall`), so the website and the assistant
share one set of validation rules and one audit trail.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.tools.builtin import PRESENT
from app.api.profile import identity_row
from app.api.toolcall import read_tool, run_action
from app.auth.context import AuthContext, Role
from app.auth.deps import get_db, require_roles
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

router = APIRouter(prefix="/api/faculty", tags=["faculty"])
faculty_only = require_roles(Role.FACULTY)

RECENT_SESSIONS = 10
MAX_ROLLS = 500


class AttendanceIn(BaseModel):
    date: Date
    slot_no: int | None = Field(default=None, ge=1, le=12)
    absent_roll_nos: list[str] = Field(default_factory=list, max_length=MAX_ROLLS)


class MarksIn(BaseModel):
    marks: dict[str, float] = Field(default_factory=dict, max_length=MAX_ROLLS)
    absent_roll_nos: list[str] = Field(default_factory=list, max_length=MAX_ROLLS)


# --- ownership ----------------------------------------------------------------


def _own(db: Session, ctx: AuthContext, offering_id: int) -> CourseOffering:
    offering = db.scalar(
        select(CourseOffering).where(
            CourseOffering.id == offering_id,
            CourseOffering.faculty_id == ctx.faculty_id,
            CourseOffering.term == ctx.term,
        )
    )
    if offering is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such course")
    return offering


def _own_assessment(db: Session, ctx: AuthContext, assessment_id: int) -> tuple[Assessment, CourseOffering]:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such assessment")
    return assessment, _own(db, ctx, assessment.offering_id)  # a foreign assessment is the same 404


def _enrolled(offering_id: int):
    return (
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.offering_id == offering_id, Enrollment.status == "enrolled")
        .order_by(Student.roll_no)
    )


def _offering_out(o: CourseOffering, enrolled: int | None = None) -> dict[str, Any]:
    return {
        "offering_id": o.id,
        "course": o.subject_code,
        "name": o.subject_name,
        "dept_code": o.dept_code,
        "semester": o.semester,
        "division": o.division,
        "lab_group": o.lab_group,
        "session_type": o.session_type,
        "enrolled": enrolled,
    }


# --- courses and roster -------------------------------------------------------


@router.get("/courses")
def courses(ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    enrolled = (
        select(func.count(Enrollment.id))
        .where(Enrollment.offering_id == CourseOffering.id, Enrollment.status == "enrolled")
        .scalar_subquery()
    )
    rows = db.execute(
        select(CourseOffering, enrolled.label("enrolled"))
        .where(CourseOffering.faculty_id == ctx.faculty_id, CourseOffering.term == ctx.term)
        .order_by(CourseOffering.subject_code, CourseOffering.dept_code, CourseOffering.division, CourseOffering.lab_group)
    )
    return [_offering_out(o, n) for o, n in rows]


@router.get("/offerings/{offering_id}/roster")
def roster(offering_id: int, ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)) -> dict[str, Any]:
    offering = _own(db, ctx, offering_id)
    students = list(db.scalars(_enrolled(offering.id)))

    att = {
        r.student_id: (r.attended, r.total)
        for r in db.execute(
            select(
                AttendanceRecord.student_id,
                func.count(AttendanceRecord.id).filter(AttendanceRecord.status.in_(PRESENT)).label("attended"),
                func.count(AttendanceRecord.id).label("total"),
            )
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .where(AttendanceSession.offering_id == offering.id)
            .group_by(AttendanceRecord.student_id)
        )
    }
    missing = dict(
        db.execute(
            select(Submission.student_id, func.count(Submission.id))
            .join(Assessment, Assessment.id == Submission.assessment_id)
            .where(Assessment.offering_id == offering.id, Submission.status == "missing")
            .group_by(Submission.student_id)
        ).all()
    )
    out = []
    for s in students:
        attended, total = att.get(s.id, (0, 0))
        out.append(
            {
                "roll_no": s.roll_no,
                "full_name": s.full_name,
                "dept_code": s.dept_code,
                "division": s.division,
                "attended": attended,
                "total": total,
                "attendance_percent": round(attended * 100.0 / total, 1) if total else None,
                "missing_submissions": missing.get(s.id, 0),
            }
        )
    return {"offering": _offering_out(offering, len(out)), "students": out}


# --- attendance ---------------------------------------------------------------


@router.get("/offerings/{offering_id}/attendance")
def attendance(
    offering_id: int,
    date: Date | None = Query(default=None, description="a day to look up; omit for the history only"),
    ctx: AuthContext = Depends(faculty_only),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    offering = _own(db, ctx, offering_id)

    def _summary(session: AttendanceSession) -> dict[str, Any]:
        absent = list(
            db.scalars(
                select(Student.roll_no)
                .join(AttendanceRecord, AttendanceRecord.student_id == Student.id)
                .where(AttendanceRecord.session_id == session.id, AttendanceRecord.status == "absent")
                .order_by(Student.roll_no)
            )
        )
        total = db.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.session_id == session.id)) or 0
        return {
            "id": session.id,
            "date": session.session_date.isoformat(),
            "slot_no": session.slot_no,
            "marked_at": session.marked_at.isoformat() if session.marked_at else None,
            "present": total - len(absent),
            "absent": len(absent),
            "absent_roll_nos": absent,
        }

    base = select(AttendanceSession).where(AttendanceSession.offering_id == offering.id)
    recent = db.scalars(base.order_by(AttendanceSession.session_date.desc(), AttendanceSession.slot_no.desc()).limit(RECENT_SESSIONS))
    on_day = (
        db.scalars(base.where(AttendanceSession.session_date == date).order_by(AttendanceSession.slot_no))
        if date
        else []
    )
    return {
        "offering": _offering_out(offering),
        "date": date.isoformat() if date else None,
        "sessions": [_summary(s) for s in on_day],
        "recent": [_summary(s) for s in recent],
    }


@router.post("/offerings/{offering_id}/attendance", status_code=status.HTTP_201_CREATED)
def mark_attendance(
    offering_id: int, body: AttendanceIn, ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)
) -> dict[str, Any]:
    offering = _own(db, ctx, offering_id)
    return run_action(
        db,
        ctx,
        "mark_attendance",
        {
            "course_code": offering.subject_code,
            "date": body.date.isoformat(),
            "absent_roll_nos": body.absent_roll_nos,
            "slot_no": body.slot_no,
            "offering_id": offering.id,
        },
    )


@router.put("/offerings/{offering_id}/attendance")
def correct_attendance(
    offering_id: int, body: AttendanceIn, ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)
) -> dict[str, Any]:
    offering = _own(db, ctx, offering_id)
    return run_action(
        db,
        ctx,
        "correct_attendance",
        {
            "course_code": offering.subject_code,
            "date": body.date.isoformat(),
            "absent_roll_nos": body.absent_roll_nos,
            "slot_no": body.slot_no,
            "offering_id": offering.id,
        },
    )


# --- marks --------------------------------------------------------------------


@router.get("/offerings/{offering_id}/assessments")
def assessments(offering_id: int, ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)) -> dict[str, Any]:
    offering = _own(db, ctx, offering_id)
    enrolled = db.scalar(
        select(func.count(Enrollment.id)).where(Enrollment.offering_id == offering.id, Enrollment.status == "enrolled")
    )
    graded = dict(
        db.execute(
            select(Mark.assessment_id, func.count(Mark.id))
            .join(Assessment, Assessment.id == Mark.assessment_id)
            .where(Assessment.offering_id == offering.id, (Mark.score.isnot(None)) | (Mark.is_absent.is_(True)))
            .group_by(Mark.assessment_id)
        ).all()
    )
    rows = db.scalars(select(Assessment).where(Assessment.offering_id == offering.id).order_by(Assessment.due_date, Assessment.id))
    return {
        "offering": _offering_out(offering, enrolled),
        "assessments": [
            {
                "assessment_id": a.id,
                "type": a.type,
                "title": a.title,
                "max_marks": float(a.max_marks) if a.max_marks is not None else None,
                "weightage_pct": float(a.weightage_pct) if a.weightage_pct is not None else None,
                "due_date": a.due_date.isoformat() if a.due_date else None,
                "status": a.status,
                "graded": graded.get(a.id, 0),
            }
            for a in rows
        ],
    }


@router.get("/assessments/{assessment_id}/marks")
def marks(assessment_id: int, ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)) -> dict[str, Any]:
    assessment, offering = _own_assessment(db, ctx, assessment_id)
    existing = {m.student_id: m for m in db.scalars(select(Mark).where(Mark.assessment_id == assessment.id))}
    return {
        "offering": _offering_out(offering),
        "assessment": {
            "assessment_id": assessment.id,
            "type": assessment.type,
            "title": assessment.title,
            "max_marks": float(assessment.max_marks) if assessment.max_marks is not None else None,
        },
        "students": [
            {
                "roll_no": s.roll_no,
                "full_name": s.full_name,
                "score": float(existing[s.id].score) if s.id in existing and existing[s.id].score is not None else None,
                "is_absent": bool(s.id in existing and existing[s.id].is_absent),
            }
            for s in db.scalars(_enrolled(offering.id))
        ],
    }


@router.post("/assessments/{assessment_id}/marks")
def save_marks(
    assessment_id: int, body: MarksIn, ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)
) -> dict[str, Any]:
    assessment, offering = _own_assessment(db, ctx, assessment_id)
    return run_action(
        db,
        ctx,
        "enter_marks",
        {
            "course_code": offering.subject_code,
            "assessment": assessment.type,
            "marks": body.marks,
            "absent_roll_nos": body.absent_roll_nos,
            "offering_id": offering.id,
        },
    )


# --- dashboard ----------------------------------------------------------------


@router.get("/dashboard")
def dashboard(ctx: AuthContext = Depends(faculty_only), db: Session = Depends(get_db)) -> dict[str, Any]:
    me = identity_row(db, ctx)
    today = Date.today()
    mine = CourseOffering.faculty_id == ctx.faculty_id, CourseOffering.term == ctx.term

    courses_n = db.scalar(select(func.count(CourseOffering.id)).where(*mine))
    students_n = db.scalar(
        select(func.count(func.distinct(Enrollment.student_id)))
        .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
        .where(*mine, Enrollment.status == "enrolled")
    )

    marked_today = set(
        db.scalars(
            select(AttendanceSession.offering_id)
            .join(CourseOffering, CourseOffering.id == AttendanceSession.offering_id)
            .where(*mine, AttendanceSession.session_date == today)
        )
    )
    slots = db.execute(
        select(TimetableSlot, CourseOffering, Classroom.code.label("room"))
        .join(CourseOffering, CourseOffering.id == TimetableSlot.offering_id)
        .outerjoin(Classroom, Classroom.id == TimetableSlot.classroom_id)
        .where(*mine, TimetableSlot.day_of_week == today.weekday())
        .order_by(TimetableSlot.start_time)
    )
    today_classes = [
        {
            **_offering_out(o),
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "room": room,
            "attendance_marked": o.id in marked_today,
        }
        for slot, o, room in slots
    ]

    at_risk = read_tool("identify_at_risk_students", ctx, db)
    leave = read_tool("list_pending_leave_requests", ctx, db)
    return {
        "faculty": {
            "full_name": me.full_name,
            "designation": me.designation,
            "dept_code": me.dept_code,
            "is_hod": bool(me.is_hod),
        },
        "term": ctx.term,
        "date": today.isoformat(),
        "weekday": today.weekday(),
        "courses": courses_n,
        "students": students_n,
        "today": today_classes,
        "at_risk": {"count": len(at_risk), "students": at_risk[:5]},
        "pending_leave": {"count": len(leave), "requests": leave[:5]},
        "announcements": read_tool("get_my_announcements", ctx, db)[:5],
    }
