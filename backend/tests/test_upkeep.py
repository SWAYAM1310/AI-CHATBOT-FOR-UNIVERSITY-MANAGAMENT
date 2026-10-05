"""The upkeep job: unmarked classes recorded present, past assessments given marks from
each student's own range, stale statuses settled. Each test runs the job inside a
transaction and rolls it back, so the sample data stays as loaded.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.db.session import SessionLocal
from app.jobs.upkeep import run_upkeep
from app.models import (
    Assessment,
    AttendanceRecord,
    AttendanceSession,
    Enrollment,
    ExamSchedule,
    Fee,
    LeaveRequest,
    Mark,
    TimetableSlot,
)

TERM = settings.current_term
TODAY = date(2026, 10, 6)  # so everything up to Monday 5 Oct is settled
CUTOFF = TODAY - timedelta(days=1)
NO_CLASS_DAYS = {date(2026, 8, 15), date(2026, 8, 26), date(2026, 9, 5), date(2026, 10, 2)}  # holidays
EXAM_WEEKS = [(date(2026, 8, 20), date(2026, 8, 25))]  # the mid-semester exam


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s
        s.rollback()


def _auto_sessions(db) -> list[AttendanceSession]:
    return list(db.scalars(select(AttendanceSession).where(AttendanceSession.auto_marked.is_(True))))


def test_unmarked_classes_are_recorded_with_everyone_present(db):
    assert not _auto_sessions(db)
    counts = run_upkeep(db, TODAY)
    auto = _auto_sessions(db)
    assert counts["classes_auto_marked"] == len(auto) > 0

    for s in auto:
        assert s.session_date <= CUTOFF and s.marked_by is None
        assert s.session_date not in NO_CLASS_DAYS
        assert not any(lo <= s.session_date <= hi for lo, hi in EXAM_WEEKS)
        weekdays = set(db.scalars(select(TimetableSlot.day_of_week).where(TimetableSlot.offering_id == s.offering_id)))
        assert s.session_date.weekday() in weekdays

    # one session per class and day, never beside one a faculty member took
    per_day = db.execute(
        select(AttendanceSession.offering_id, AttendanceSession.session_date, func.count())
        .group_by(AttendanceSession.offering_id, AttendanceSession.session_date)
        .having(func.count() > 1, func.bool_or(AttendanceSession.auto_marked))
    ).all()
    assert per_day == []

    # every enrolled student present; nobody who dropped the course
    sample = auto[0]
    statuses = list(db.scalars(select(AttendanceRecord.status).where(AttendanceRecord.session_id == sample.id)))
    enrolled = db.scalar(
        select(func.count()).where(Enrollment.offering_id == sample.offering_id, Enrollment.status == "enrolled")
    )
    assert statuses and set(statuses) == {"present"} and len(statuses) == enrolled
    dropped_marked = db.scalar(
        select(func.count())
        .select_from(AttendanceRecord)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(
            Enrollment,
            (Enrollment.offering_id == AttendanceSession.offering_id) & (Enrollment.student_id == AttendanceRecord.student_id),
        )
        .where(AttendanceSession.auto_marked.is_(True), Enrollment.status == "dropped")
    )
    assert dropped_marked == 0


def test_today_stays_open_until_it_is_over_unless_asked(db):
    monday = date(2026, 10, 5)
    run_upkeep(db, monday)
    assert not [s for s in _auto_sessions(db) if s.session_date == monday]
    run_upkeep(db, monday, through=monday)
    assert [s for s in _auto_sessions(db) if s.session_date == monday]


def test_past_assessments_get_half_step_marks_inside_each_students_range(db):
    share = Mark.score / Assessment.max_marks
    ranges = {
        sid: (lo, hi)
        for sid, lo, hi in db.execute(
            select(Mark.student_id, func.min(share), func.max(share))
            .join(Assessment, Assessment.id == Mark.assessment_id)
            .where(Assessment.term == TERM, Mark.score.isnot(None), Mark.is_absent.is_(False))
            .group_by(Mark.student_id)
        )
    }
    counts = run_upkeep(db, TODAY)
    graded = list(db.scalars(select(Assessment).where(Assessment.auto_graded.is_(True))))
    assert counts["assessments_auto_graded"] == len(graded) > 0
    assert "Lab-File" in {a.type for a in graded}  # due a week before the practical exam, nobody entered it

    for a in graded:
        assert a.due_date <= CUTOFF and a.status == "graded"
        marks = list(db.scalars(select(Mark).where(Mark.assessment_id == a.id)))
        enrolled = db.scalar(select(func.count()).where(Enrollment.offering_id == a.offering_id, Enrollment.status == "enrolled"))
        assert len(marks) == enrolled
        for m in marks:
            assert m.score * 2 == int(m.score * 2) and Decimal(0) <= m.score <= a.max_marks
            assert m.graded_on <= TODAY
            if m.student_id in ranges:  # rounding to a half mark can step just outside
                lo, hi = ranges[m.student_id]
                assert lo * a.max_marks - Decimal("0.25") <= m.score <= hi * a.max_marks + Decimal("0.25")

    later = db.scalar(select(func.count()).where(Assessment.auto_graded.is_(True), Assessment.due_date > CUTOFF))
    assert later == 0


def test_a_second_run_changes_nothing(db):
    run_upkeep(db, TODAY)
    again = run_upkeep(db, TODAY)
    assert set(again.values()) == {0}, again


def test_stale_statuses_are_settled(db):
    future_pending = db.scalar(
        select(func.count()).where(LeaveRequest.status == "pending", LeaveRequest.from_date > CUTOFF)
    )
    run_upkeep(db, TODAY)
    assert db.scalar(select(func.count()).where(Fee.status.in_(("unpaid", "partial")), Fee.due_date <= CUTOFF)) == 0
    assert db.scalar(select(func.count()).where(ExamSchedule.exam_date <= CUTOFF, ExamSchedule.status != "completed")) == 0
    assert db.scalar(select(func.count()).where(ExamSchedule.exam_date > CUTOFF, ExamSchedule.status == "completed")) == 0
    assert db.scalar(select(func.count()).where(Enrollment.term == "2025-26-EVEN", Enrollment.status == "enrolled")) == 0
    assert db.scalar(select(func.count()).where(Enrollment.term == TERM, Enrollment.status == "completed")) == 0
    assert db.scalar(select(func.count()).where(LeaveRequest.status == "pending", LeaveRequest.from_date <= CUTOFF)) == 0
    assert db.scalar(select(func.count()).where(LeaveRequest.status == "pending")) == future_pending


def test_correcting_an_auto_register_hands_it_to_the_faculty_member(db):
    from app.ai.tools.registry import REGISTRY
    from app.models import CourseOffering, Student
    from tests.conftest import make_ctx

    run_upkeep(db, TODAY)
    session = _auto_sessions(db)[0]
    offering = db.get(CourseOffering, session.offering_id)
    roll = db.scalar(
        select(Student.roll_no)
        .join(AttendanceRecord, AttendanceRecord.student_id == Student.id)
        .where(AttendanceRecord.session_id == session.id)
        .limit(1)
    )
    done = REGISTRY.invoke(
        "correct_attendance",
        make_ctx("faculty", offering.faculty_id),
        db,
        {"offering_id": offering.id, "course_code": offering.subject_code, "date": session.session_date.isoformat(), "absent_roll_nos": [roll]},
        confirmed=True,
    )
    assert done["done"] and done["changed"] == 1
    assert session.auto_marked is False and session.marked_by == offering.faculty_id
