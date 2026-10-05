"""Student portal: one payload that is the whole Home page.

Built from the student's own read tools (see `app.api.toolcall.read_tool`), so
the page and the assistant quote the same numbers, and a faculty member's
attendance entry shows up here the moment it is committed. Identity comes from
the token; there is no student id anywhere in the request.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.ai.cards import ATTENDANCE_THRESHOLD
from app.api.profile import identity_row
from app.api.toolcall import read_tool
from app.auth.context import AuthContext, Role
from app.auth.deps import get_db, require_roles
from app.models import Assessment, CourseOffering, Enrollment, Mark, ResultSemester, Subject

router = APIRouter(prefix="/api/student", tags=["student"])



def _attendance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-course rows plus the arithmetic a student actually wants: how far from the floor."""
    floor = ATTENDANCE_THRESHOLD / 100
    courses = []
    for r in rows:
        attended, total = r["attended"], r["total"]
        below = total > 0 and attended / total < floor
        course = {**r, "below_threshold": below, "recover": None, "can_skip": None}
        if below:
            # classes to attend in a row to get back to the floor: (a + x) / (t + x) >= floor
            course["recover"] = math.ceil((floor * total - attended) / (1 - floor))
        elif total:
            # classes that can still be missed and stay at the floor: a / (t + m) >= floor
            course["can_skip"] = math.floor(attended / floor - total)
        courses.append(course)
    attended, total = sum(r["attended"] for r in rows), sum(r["total"] for r in rows)
    return {
        "threshold": ATTENDANCE_THRESHOLD,
        "overall_percent": round(attended * 100.0 / total, 1) if total else None,
        "short_courses": sum(1 for c in courses if c["below_threshold"]),
        "courses": courses,
    }


def _fees(rows: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [
        {**r, "outstanding": round((r["amount_due"] or 0) - (r["amount_paid"] or 0), 2)} for r in rows
    ]
    outstanding = round(sum(e["outstanding"] for e in entries if e["status"] != "paid"), 2)
    return {
        "all_paid": all(e["status"] == "paid" for e in entries) if entries else True,
        "outstanding": max(outstanding, 0.0),
        "entries": entries,
    }


@router.get("/dashboard")
def dashboard(ctx: AuthContext = Depends(require_roles(Role.STUDENT)), db: Session = Depends(get_db)) -> dict[str, Any]:
    me = identity_row(db, ctx)
    today = date.today()
    return {
        "student": {
            "full_name": me.full_name,
            "roll_no": me.roll_no,
            "dept_code": me.dept_code,
            "semester": me.semester,
            "division": me.division,
            "cgpa": float(me.cgpa) if me.cgpa is not None else None,
        },
        "term": ctx.term,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": today.isoformat(),
        "weekday": today.weekday(),
        "attendance": _attendance(read_tool("get_my_attendance", ctx, db)),
        "fees": _fees(read_tool("get_my_fees", ctx, db)),
        "assignments": read_tool("get_my_assignments", ctx, db),
        "exams": read_tool("get_my_exam_schedule", ctx, db),
        "today": read_tool("get_my_timetable", ctx, db, day=today.weekday()),
        "announcements": read_tool("get_my_announcements", ctx, db)[:10],
    }


def _num(v: Any) -> float | None:
    return float(v) if v is not None else None


def _course_total(assessments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The course total out of 100: each component's mark scaled to its weightage, so an
    End-Sem written out of 100 counts as 50. Only once every component has a mark (absent
    counts as zero); a partial total would read as a low one."""
    weighted = [a for a in assessments if a["weightage_pct"] and a["max_marks"]]
    if not weighted or not all(a["is_absent"] or a["score"] is not None for a in weighted):
        return None
    score = sum(0.0 if a["is_absent"] else a["score"] / a["max_marks"] * a["weightage_pct"] for a in weighted)
    return {"score": round(score, 2), "out_of": sum(a["weightage_pct"] for a in weighted)}


@router.get("/results")
def results(ctx: AuthContext = Depends(require_roles(Role.STUDENT)), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Every semester the student has been enrolled in, newest first: each course's assessments
    (including those not held yet), its total once all are marked, and the declared semester result."""
    rows = db.execute(
        select(
            CourseOffering.term,
            CourseOffering.semester,
            CourseOffering.subject_code,
            CourseOffering.subject_name,
            Subject.component,
            Assessment.type,
            Assessment.title,
            Assessment.max_marks,
            Assessment.weightage_pct,
            Assessment.due_date,
            Assessment.status,
            Mark.id.label("mark_id"),
            Mark.score,
            Mark.is_absent,
        )
        .select_from(Enrollment)
        .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
        .join(Subject, Subject.subject_code == CourseOffering.subject_code)
        .outerjoin(Assessment, Assessment.offering_id == CourseOffering.id)
        .outerjoin(Mark, and_(Mark.assessment_id == Assessment.id, Mark.student_id == ctx.student_id))
        .where(Enrollment.student_id == ctx.student_id, Enrollment.status != "dropped")
        .order_by(CourseOffering.semester.desc(), CourseOffering.subject_code, Assessment.due_date, Assessment.id)
    ).all()

    semesters: dict[tuple[str, int], dict[str, Any]] = {}
    for r in rows:
        sem = semesters.setdefault(
            (r.term, r.semester),
            {"semester": r.semester, "term": r.term, "current": r.term == ctx.term, "result": None, "courses": {}},
        )
        course = sem["courses"].setdefault(
            r.subject_code,
            {"course": r.subject_code, "name": r.subject_name, "component": r.component, "assessments": []},
        )
        if r.type is None:  # a course with no assessments set yet
            continue
        course["assessments"].append(
            {
                "type": r.type,
                "title": r.title,
                "max_marks": _num(r.max_marks),
                "weightage_pct": _num(r.weightage_pct),
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "status": r.status,
                "entered": r.mark_id is not None,
                "score": _num(r.score),
                "is_absent": bool(r.is_absent),
            }
        )

    declared = db.scalars(select(ResultSemester).where(ResultSemester.student_id == ctx.student_id)).all()
    for res in declared:
        sem = semesters.get((res.term, res.semester))
        if sem is not None:
            sem["result"] = {
                "sgpa": _num(res.sgpa),
                "cgpa": _num(res.cgpa),
                "result_status": res.result_status,
                "credits_earned": res.credits_earned,
                "credits_registered": res.credits_registered,
                "backlogs": res.backlogs,
                "declared_on": res.declared_on.isoformat() if res.declared_on else None,
            }

    out = []
    for sem in semesters.values():
        courses = list(sem["courses"].values())
        for c in courses:
            c["total"] = _course_total(c["assessments"])
        out.append({**sem, "courses": courses})
    return {"term": ctx.term, "semesters": out}
