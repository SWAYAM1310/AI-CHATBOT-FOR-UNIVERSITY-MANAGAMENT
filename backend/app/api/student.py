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
from sqlalchemy.orm import Session

from app.ai.cards import ATTENDANCE_THRESHOLD
from app.api.profile import identity_row
from app.api.toolcall import read_tool
from app.auth.context import AuthContext, Role
from app.auth.deps import get_db, require_roles

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
        "marks": read_tool("get_my_marks", ctx, db),
        "fees": _fees(read_tool("get_my_fees", ctx, db)),
        "assignments": read_tool("get_my_assignments", ctx, db),
        "exams": read_tool("get_my_exam_schedule", ctx, db),
        "today": read_tool("get_my_timetable", ctx, db, day=today.weekday()),
        "announcements": read_tool("get_my_announcements", ctx, db)[:10],
    }
