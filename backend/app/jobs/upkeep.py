"""Keep the records moving with the calendar, so nobody has to tidy them by hand.

Once a day is over, everything dated on it is settled:

- **Attendance.** A timetabled class nobody took the register for is recorded with
  every enrolled student present (`auto_marked`). A faculty member can still correct it.
- **Marks.** An assessment whose day has passed with no marks gets them (`auto_graded`).
  A student's score is a random point in their own range this semester, the lowest
  and highest share of max marks they have scored, scaled to this assessment and
  rounded to a half mark.
- **Statuses.** Exams that took place become completed. Fees still unpaid or part paid
  after their due date become overdue. A term's enrollments complete once its results
  are declared. Leave requests nobody decided before they began become expired.

Every step only touches what is still unsettled, so running it again changes nothing.
It runs when the API starts and every few minutes after that (app/main.py), and by hand:

    python -m app.jobs.upkeep                      # settle everything up to yesterday
    python -m app.jobs.upkeep --through 2026-10-05 # ...or up to and including a day
"""
from __future__ import annotations

import argparse
import math
import random
from collections import defaultdict
from datetime import date as Date
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, exists, func, insert, select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.models import (
    AcademicCalendarEvent,
    Assessment,
    AttendanceRecord,
    AttendanceSession,
    CourseOffering,
    Enrollment,
    ExamSchedule,
    Fee,
    LeaveRequest,
    Mark,
    TimetableSlot,
)
from app.schedule import events_between, is_teaching_day, term_window

# Held by whoever is writing: two API processes never run the job together, and a pytest
# session (tests/conftest.py) keeps it off the shared dev database while tests run.
LOCK_KEY = 7_726_001
FALLBACK_RANGE = (0.40, 0.90)  # share of max marks, for a class with no marks at all yet
GRADING_LAG = timedelta(days=5)  # marks appear a few days after the assessment


def half_step(x: float) -> Decimal:
    """Marks are whole or half (7, 7.5), never 7.3."""
    return Decimal(math.floor(x * 2 + 0.5)) / 2


def run_upkeep(db: Session, today: Date, through: Date | None = None) -> dict[str, int]:
    """Settle everything dated on or before `through` (default: yesterday). Does not commit."""
    cutoff = through or today - timedelta(days=1)
    term = settings.current_term
    counts: dict[str, int] = {}
    counts["classes_auto_marked"], counts["attendance_records"] = _fill_attendance(db, term, cutoff)
    counts["assessments_auto_graded"], counts["marks"] = _fill_marks(db, term, cutoff, today)
    counts.update(_settle_statuses(db, cutoff))
    return counts


# --- attendance ----------------------------------------------------------------------------


def _fill_attendance(db: Session, term: str, cutoff: Date) -> tuple[int, int]:
    start, end = term_window(db, term)
    if start is None or end is None or cutoff < start:
        return 0, 0
    last = min(cutoff, end)
    events = events_between(db, term, start, last)

    meets: dict[int, set[int]] = defaultdict(set)  # weekday -> offerings timetabled that day
    code: dict[int, str] = {}
    for oid, subject, weekday in db.execute(
        select(CourseOffering.id, CourseOffering.subject_code, TimetableSlot.day_of_week)
        .join(TimetableSlot, TimetableSlot.offering_id == CourseOffering.id)
        .where(CourseOffering.term == term)
        .distinct()
    ):
        meets[weekday].add(oid)
        code[oid] = subject
    if not code:
        return 0, 0

    roster: dict[int, list[int]] = defaultdict(list)
    for oid, sid in db.execute(
        select(Enrollment.offering_id, Enrollment.student_id).where(
            Enrollment.offering_id.in_(code), Enrollment.status == "enrolled"
        )
    ):
        roster[oid].append(sid)
    held = set(
        db.execute(
            select(AttendanceSession.offering_id, AttendanceSession.session_date).where(
                AttendanceSession.offering_id.in_(code), AttendanceSession.session_date.between(start, last)
            )
        ).tuples()
    )

    missed = []
    d = start
    while d <= last:
        if is_teaching_day(d, events, start, end):
            missed += [(oid, d) for oid in sorted(meets[d.weekday()]) if roster[oid] and (oid, d) not in held]
        d += timedelta(days=1)
    if not missed:
        return 0, 0

    session_ids = db.scalars(
        insert(AttendanceSession).returning(AttendanceSession.id, sort_by_parameter_order=True),
        [
            {
                "offering_id": oid,
                "subject_code": code[oid],
                "session_date": d,
                "slot_no": None,
                "marked_by": None,
                "marked_at": datetime.combine(d, time(23, 59)),
                "auto_marked": True,
            }
            for oid, d in missed
        ],
    ).all()
    records = [
        {"session_id": session_id, "student_id": sid, "status": "present"}
        for session_id, (oid, _) in zip(session_ids, missed)
        for sid in roster[oid]
    ]
    db.execute(insert(AttendanceRecord), records)
    return len(missed), len(records)


# --- marks -----------------------------------------------------------------------------------


def _fill_marks(db: Session, term: str, cutoff: Date, today: Date) -> tuple[int, int]:
    pending = list(
        db.scalars(
            select(Assessment)
            .where(
                Assessment.term == term,
                Assessment.due_date <= cutoff,
                Assessment.max_marks > 0,
                ~exists().where(Mark.assessment_id == Assessment.id),
            )
            .order_by(Assessment.id)
        )
    )
    if not pending:
        return 0, 0

    # each student's range this semester, and each class's, as a share of max marks
    share = Mark.score / Assessment.max_marks
    scored = and_(Assessment.term == term, Mark.score.isnot(None), Mark.is_absent.is_(False), Assessment.max_marks > 0)
    own = {
        sid: (float(lo), float(hi))
        for sid, lo, hi in db.execute(
            select(Mark.student_id, func.min(share), func.max(share))
            .join(Assessment, Assessment.id == Mark.assessment_id)
            .where(scored)
            .group_by(Mark.student_id)
        )
    }
    by_class = {
        oid: (float(lo), float(hi))
        for oid, lo, hi in db.execute(
            select(Assessment.offering_id, func.min(share), func.max(share))
            .join(Mark, Mark.assessment_id == Assessment.id)
            .where(scored)
            .group_by(Assessment.offering_id)
        )
    }
    roster: dict[int, list[int]] = defaultdict(list)
    for oid, sid in db.execute(
        select(Enrollment.offering_id, Enrollment.student_id)
        .where(Enrollment.offering_id.in_({a.offering_id for a in pending}), Enrollment.status == "enrolled")
        .order_by(Enrollment.student_id)
    ):
        roster[oid].append(sid)

    rows, graded = [], []
    for a in pending:
        top = float(a.max_marks)
        graded_on = min(a.due_date + GRADING_LAG, today)
        for sid in roster[a.offering_id]:
            lo, hi = own.get(sid) or by_class.get(a.offering_id) or FALLBACK_RANGE
            rng = random.Random(f"{a.id}:{sid}")  # the same score on every run
            score = min(Decimal(str(top)), max(Decimal(0), half_step(rng.uniform(lo, hi) * top)))
            rows.append({"assessment_id": a.id, "student_id": sid, "score": score, "is_absent": False, "graded_on": graded_on})
        if roster[a.offering_id]:
            graded.append(a.id)
    if rows:
        db.execute(insert(Mark), rows)
    if graded:
        db.execute(update(Assessment).where(Assessment.id.in_(graded)).values(status="graded", auto_graded=True))
    return len(graded), len(rows)


# --- statuses --------------------------------------------------------------------------------


def _settle_statuses(db: Session, cutoff: Date) -> dict[str, int]:
    declared = select(AcademicCalendarEvent.term).where(
        AcademicCalendarEvent.event_type == "result", AcademicCalendarEvent.start_date <= cutoff
    )
    changes = {
        "exams_completed": update(ExamSchedule)
        .where(ExamSchedule.exam_date <= cutoff, ExamSchedule.status != "completed")
        .values(status="completed"),
        "fees_overdue": update(Fee)
        .where(Fee.status.in_(("unpaid", "partial")), Fee.due_date <= cutoff)
        .values(status="overdue"),
        "enrollments_completed": update(Enrollment)
        .where(Enrollment.status == "enrolled", Enrollment.term.in_(declared))
        .values(status="completed"),
        "leave_expired": update(LeaveRequest)
        .where(LeaveRequest.status == "pending", LeaveRequest.from_date <= cutoff)
        .values(status="expired"),
    }
    return {name: db.execute(stmt.execution_options(synchronize_session=False)).rowcount for name, stmt in changes.items()}


# --- running it ------------------------------------------------------------------------------


def run_now(through: Date | None = None) -> dict[str, int] | None:
    """Run the job in its own transaction. None when another process holds the lock."""
    with SessionLocal() as db:
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY}):
            return None
        counts = run_upkeep(db, Date.today(), through)
        db.commit()
    return counts


def describe(counts: dict[str, int] | None) -> str:
    if counts is None:
        return "skipped: another process holds the lock"
    changed = [f"{name.replace('_', ' ')} {n}" for name, n in counts.items() if n]
    return ", ".join(changed) or "nothing to settle"


def main() -> None:
    ap = argparse.ArgumentParser(description="Settle attendance, marks and statuses up to a day.")
    ap.add_argument("--through", type=Date.fromisoformat, help="last day to settle (default: yesterday)")
    args = ap.parse_args()
    counts = run_now(args.through)
    if counts is None:
        raise SystemExit("another process is running the upkeep job (or a test session holds its lock)")
    for name, n in counts.items():
        print(f"{name:<26} {n:>7}")


if __name__ == "__main__":
    main()
