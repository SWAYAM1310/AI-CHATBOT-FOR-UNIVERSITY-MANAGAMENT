"""Phase 2 step 7b — admin UNIVERSITY read tools (plan.md §6).

Real DB, no LLM. The interesting property is that `run_analytics` is bounded:
it is the only "open-ended" tool and it must reject anything outside its enums.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.ai.tools.admin_tools import GROUP_BY, LIST_CAP, METRICS
from app.ai.tools.registry import REGISTRY, ToolDenied
from app.auth.context import Role
from app.db.session import SessionLocal
from app.models import Student
from tests.conftest import make_ctx

ADMIN_TOOLS = {
    "get_enrollment_stats",
    "get_department_overview",
    "get_course_performance",
    "list_students",
    "get_university_attendance_report",
    "get_faculty_workload",
    "find_available_classrooms",
    "get_fee_collection_summary",
    "run_analytics",
}
DBMS = "24CS201T"
A_MONDAY = "2026-09-14"
A_SUNDAY = "2026-09-13"


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def admin():
    return make_ctx("admin")


# --- exposure --------------------------------------------------------------

def test_admin_group_is_admin_only():
    assert ADMIN_TOOLS <= {t["name"] for t in REGISTRY.index_for(Role.ADMIN)}
    assert not ADMIN_TOOLS & {t["name"] for t in REGISTRY.index_for(Role.FACULTY)}
    assert not ADMIN_TOOLS & {t["name"] for t in REGISTRY.index_for(Role.STUDENT)}


@pytest.mark.parametrize("role", ["student", "faculty"])
def test_run_analytics_is_denied_to_non_admins(role, db):
    with pytest.raises(ToolDenied):
        REGISTRY.invoke("run_analytics", make_ctx(role), db, {"metric": "student_count", "group_by": "department"})


# --- aggregates agree with the raw tables -------------------------------------

def test_enrollment_stats_sum_to_the_active_headcount(db, admin):
    rows = REGISTRY.invoke("get_enrollment_stats", admin, db)
    active = db.scalar(select(func.count(Student.id)).where(Student.is_active.is_(True)))
    assert sum(r["students"] for r in rows) == active
    only_cp = REGISTRY.invoke("get_enrollment_stats", admin, db, {"dept": "cp"})  # case-insensitive
    assert only_cp and all(r["dept"] == "CP" for r in only_cp)


def test_department_overview_has_every_department_with_a_hod(db, admin):
    rows = REGISTRY.invoke("get_department_overview", admin, db)
    assert len(rows) == 7
    assert all(r["hod"] for r in rows)
    assert sum(r["students"] for r in rows) == db.scalar(
        select(func.count(Student.id)).where(Student.is_active.is_(True))
    )


def test_course_performance_matches_the_faculty_view_of_the_same_course(db, admin):
    (row,) = REGISTRY.invoke("get_course_performance", admin, db, {"course": DBMS})
    faculty_view = REGISTRY.invoke("get_course_attendance_summary", make_ctx("faculty", 2), db, {"course_code": DBMS})
    assert row["avg_attendance_percent"] == faculty_view["average_percent"]
    assert row["enrolled"] == faculty_view["students"]


def test_list_students_filters_and_is_capped(db, admin):
    rows = REGISTRY.invoke("list_students", admin, db, {"dept": "IT", "min_cgpa": 8.0})
    assert rows and all(r["dept"] == "IT" and r["cgpa"] >= 8.0 for r in rows)
    everyone = REGISTRY.invoke("list_students", admin, db)
    assert len(everyone) == min(LIST_CAP, db.scalar(select(func.count(Student.id))))


def test_attendance_report_threshold_changes_the_below_count(db, admin):
    at_75 = REGISTRY.invoke("get_university_attendance_report", admin, db)
    at_95 = REGISTRY.invoke("get_university_attendance_report", admin, db, {"threshold": 95})
    assert sum(r["below_threshold"] for r in at_95) > sum(r["below_threshold"] for r in at_75)


def test_faculty_workload_counts_are_positive_for_teaching_staff(db, admin):
    rows = REGISTRY.invoke("get_faculty_workload", admin, db, {"dept": "CP"})
    assert rows and all(r["dept"] == "CP" for r in rows)
    jadeja = next(r for r in rows if r["employee_id"] == "SOT-FAC-0002")
    assert jadeja["offerings"] > 0 and jadeja["weekly_hours"] > 0 and jadeja["students"] > 0


def test_available_classrooms_excludes_rooms_booked_at_that_time(db, admin):
    free = REGISTRY.invoke(
        "find_available_classrooms", admin, db,
        {"date": A_MONDAY, "start_time": "09:00", "end_time": "10:00"},
    )
    all_rooms = REGISTRY.invoke(
        "find_available_classrooms", admin, db,
        {"date": A_SUNDAY, "start_time": "09:00", "end_time": "10:00"},
    )
    assert all_rooms == []  # nothing is timetabled on a Sunday
    assert free and "CP-101" not in {r["room"] for r in free}  # CP-101 has a Monday 09:00 lecture in the sample
    typed = REGISTRY.invoke(
        "find_available_classrooms", admin, db,
        {"date": A_MONDAY, "start_time": "09:00", "end_time": "10:00", "room_type": "laboratory"},
    )
    assert typed and all(r["type"] == "Laboratory" for r in typed)


def test_available_classrooms_rejects_bad_input_with_an_error_row(db, admin):
    bad = REGISTRY.invoke("find_available_classrooms", admin, db, {"date": "14/09/2026", "start_time": "09:00", "end_time": "10:00"})
    assert "error" in bad
    inverted = REGISTRY.invoke("find_available_classrooms", admin, db, {"date": A_MONDAY, "start_time": "10:00", "end_time": "09:00"})
    assert "error" in inverted


def test_fee_summary_arithmetic_holds(db, admin):
    for r in REGISTRY.invoke("get_fee_collection_summary", admin, db):
        assert r["billed"] - r["collected"] == pytest.approx(r["outstanding"], abs=0.01)
        assert r["paid"] + r["partial"] + r["unpaid"] + r["overdue"] == r["bills"]
        assert 0 <= r["collection_rate_percent"] <= 100


# --- run_analytics: bounded by construction ------------------------------------

@pytest.mark.parametrize("metric", METRICS)
@pytest.mark.parametrize("group_by", list(GROUP_BY))
def test_every_metric_group_by_combination_runs(metric, group_by, db, admin):
    rows = REGISTRY.invoke("run_analytics", admin, db, {"metric": metric, "group_by": group_by})
    assert isinstance(rows, list) and rows
    assert all(r["metric"] == metric and group_by in r for r in rows)


def test_run_analytics_student_count_agrees_with_enrollment_stats(db, admin):
    by_dept = REGISTRY.invoke("run_analytics", admin, db, {"metric": "student_count", "group_by": "department"})
    stats = REGISTRY.invoke("get_enrollment_stats", admin, db)
    expected = {}
    for r in stats:
        expected[r["dept"]] = expected.get(r["dept"], 0) + r["students"]
    assert {r["department"]: r["value"] for r in by_dept} == expected


def test_run_analytics_refuses_anything_outside_its_enums(db, admin):
    for args in (
        {"metric": "median_income", "group_by": "department"},
        {"metric": "student_count", "group_by": "guardian_name"},
        {"metric": "student_count; drop table students", "group_by": "department"},
    ):
        out = REGISTRY.invoke("run_analytics", admin, db, args)
        assert isinstance(out, dict) and "allowed" in out["error"]


def test_run_analytics_filters_narrow_the_groups(db, admin):
    rows = REGISTRY.invoke(
        "run_analytics", admin, db, {"metric": "average_cgpa", "group_by": "semester", "dept": "CP", "semester": 3}
    )
    assert [r["semester"] for r in rows] == [3]
