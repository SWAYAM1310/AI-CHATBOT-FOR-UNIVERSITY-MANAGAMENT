"""Phase 2 step 7a — faculty OWN_COURSES read tools (plan.md §6).

Real DB, no LLM. Faculty 2 teaches 24CS201T (DBMS); faculty 1 does not.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai.tools.registry import REGISTRY, ToolDenied
from app.auth.context import Role
from app.db.session import SessionLocal
from app.models import AuditLog
from tests.conftest import make_ctx

DBMS = "24CS201T"
TEACHES_DBMS = 2
NOT_DBMS = 1

FACULTY_ONLY = {"get_my_teaching_courses", "get_my_teaching_schedule"}
COURSE_TOOLS = {
    "get_course_attendance_summary",
    "list_missing_submissions",
    "get_course_marks_summary",
    "identify_at_risk_students",
}


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def teacher():
    return make_ctx("faculty", TEACHES_DBMS)


@pytest.fixture()
def other():
    return make_ctx("faculty", NOT_DBMS)


# --- exposure (RBAC layer 1) -------------------------------------------------

def test_faculty_group_is_visible_to_faculty_and_hidden_from_students():
    faculty_index = {t["name"] for t in REGISTRY.index_for(Role.FACULTY)}
    student_index = {t["name"] for t in REGISTRY.index_for(Role.STUDENT)}
    admin_index = {t["name"] for t in REGISTRY.index_for(Role.ADMIN)}
    assert (FACULTY_ONLY | COURSE_TOOLS) <= faculty_index
    assert not (FACULTY_ONLY | COURSE_TOOLS) & student_index
    assert COURSE_TOOLS <= admin_index and not FACULTY_ONLY & admin_index


@pytest.mark.parametrize("name", sorted(FACULTY_ONLY | COURSE_TOOLS))
def test_student_is_denied_every_faculty_tool(name, db):
    student = make_ctx("student")
    with pytest.raises(ToolDenied):
        REGISTRY.invoke(name, student, db, {"course_code": DBMS})
    last = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).one()
    assert (last.tool_name, last.decision) == (name, "denied")


# --- OWN_COURSES gate (the thing this step is about) ------------------------

@pytest.mark.parametrize("name", sorted(COURSE_TOOLS))
def test_course_tools_return_nothing_for_a_course_you_dont_teach(name, db, teacher, other):
    mine = REGISTRY.invoke(name, teacher, db, {"course_code": DBMS})
    theirs = REGISTRY.invoke(name, other, db, {"course_code": DBMS})
    assert mine, f"{name} should have data for the teacher"
    assert theirs in ([], None)


def test_faculty_id_arg_is_stripped_so_you_cannot_borrow_a_colleagues_course(db, other):
    """Layer 3: passing the real teacher's faculty_id must not widen the gate."""
    rows = REGISTRY.invoke(
        "get_course_attendance_summary", other, db, {"course_code": DBMS, "faculty_id": TEACHES_DBMS}
    )
    assert rows is None
    last = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).one()
    assert last.decision == "arg_stripped"


# --- content ----------------------------------------------------------------

def test_teaching_courses_are_only_the_callers_offerings(db, teacher):
    rows = REGISTRY.invoke("get_my_teaching_courses", teacher, db)
    assert rows and all(r["enrolled"] >= 0 for r in rows)
    assert DBMS in {r["course"] for r in rows}
    assert DBMS not in {r["course"] for r in REGISTRY.invoke("get_my_teaching_courses", make_ctx("faculty", NOT_DBMS), db)}


def test_teaching_schedule_day_filter(db, teacher):
    week = REGISTRY.invoke("get_my_teaching_schedule", teacher, db)
    monday = REGISTRY.invoke("get_my_teaching_schedule", teacher, db, {"day": 0})
    assert week and monday
    assert all(r["day_of_week"] == 0 for r in monday)
    assert len(monday) < len(week)
    assert [(r["day_of_week"], r["start_time"]) for r in week] == sorted(
        (r["day_of_week"], r["start_time"]) for r in week
    )


def test_attendance_summary_is_consistent_with_the_below_threshold_list(db, teacher):
    summary = REGISTRY.invoke("get_course_attendance_summary", teacher, db, {"course_code": DBMS})
    below = REGISTRY.invoke("list_students_below_attendance", teacher, db, {"course_code": DBMS})
    assert summary["sessions_held"] > 0
    assert summary["below_75_percent"] == len(below)
    assert summary["lowest_percent"] == min(r["percent"] for r in below)
    assert 0 <= summary["average_percent"] <= 100


def test_missing_submissions_filters_by_assessment(db, teacher):
    every = REGISTRY.invoke("list_missing_submissions", teacher, db, {"course_code": DBMS})
    assert every and {r["status"] for r in every} <= {"missing", "late"}
    one = REGISTRY.invoke(
        "list_missing_submissions", teacher, db, {"course_code": DBMS, "assessment": "Assignment-1"}
    )
    assert one and all(r["type"] == "Assignment-1" for r in one)
    assert len(one) < len(every)


def test_marks_summary_stats_are_sane_and_filterable(db, teacher):
    rows = REGISTRY.invoke("get_course_marks_summary", teacher, db, {"course_code": DBMS})
    assert rows
    for r in rows:
        assert r["lowest"] <= r["mean"] <= r["highest"] <= r["max_marks"]
    only = REGISTRY.invoke(
        "get_course_marks_summary", teacher, db, {"course_code": DBMS, "assessment_type": "Assignment-1"}
    )
    assert [r["type"] for r in only] == ["Assignment-1"]


def test_at_risk_students_carry_reasons_and_agree_with_the_other_tools(db, teacher):
    risk = REGISTRY.invoke("identify_at_risk_students", teacher, db, {"course_code": DBMS})
    assert risk
    assert all(r["reasons"] for r in risk)
    below = {r["roll_no"] for r in REGISTRY.invoke("list_students_below_attendance", teacher, db, {"course_code": DBMS})}
    flagged_for_attendance = {r["roll_no"] for r in risk if "attendance" in r["reasons"]}
    assert flagged_for_attendance == below
    # worst first
    counts = [r["reasons"].count(";") for r in risk]
    assert counts == sorted(counts, reverse=True)
