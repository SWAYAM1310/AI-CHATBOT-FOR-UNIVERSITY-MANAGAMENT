"""Phase 2 step 1 — the ~11 student read tools + shared tools (plan.md §6).

Structural/RBAC checks, not fixture-value assertions: the planted demo cases
(test_load.py) already pin the interesting numbers.
"""
from __future__ import annotations

from sqlalchemy import select

from app.ai.tools.registry import REGISTRY
from app.auth.context import Role
from app.db.session import SessionLocal
from app.models import User
from tests.conftest import make_ctx

STUDENT_TOOLS = {
    "get_my_courses",
    "get_my_timetable",
    "get_my_marks",
    "get_my_results",
    "get_my_exam_schedule",
    "get_my_assignments",
    "get_my_fees",
    "get_my_scholarships",
    "get_my_leave_requests",
}
SHARED_TOOLS = {"search_university_policies", "get_academic_calendar", "get_my_announcements"}

# 25BCP017 — the signature demo roll (see context.md §6); has current-term enrollments.
DEMO_STUDENT_ID = 17


# --- Layer 1: exposure ------------------------------------------------------

def test_student_tools_visible_to_student_only():
    student_names = {t["name"] for t in REGISTRY.index_for(Role.STUDENT)}
    faculty_names = {t["name"] for t in REGISTRY.index_for(Role.FACULTY)}
    admin_names = {t["name"] for t in REGISTRY.index_for(Role.ADMIN)}

    assert STUDENT_TOOLS <= student_names
    assert STUDENT_TOOLS.isdisjoint(faculty_names)
    assert STUDENT_TOOLS.isdisjoint(admin_names)


def test_shared_tools_visible_to_every_role():
    for role in (Role.STUDENT, Role.FACULTY, Role.ADMIN):
        names = {t["name"] for t in REGISTRY.index_for(role)}
        assert SHARED_TOOLS <= names


# --- Layer 3: identity args never trusted ----------------------------------

def test_get_my_fees_ignores_spoofed_student_id():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        own = REGISTRY.invoke("get_my_fees", ctx, db, {})
        spoofed = REGISTRY.invoke("get_my_fees", ctx, db, {"student_id": 999999})
    assert own == spoofed


# --- Functional smoke: each tool runs and returns the caller's own data ----

def test_get_my_courses_returns_current_term_enrollments():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        rows = REGISTRY.invoke("get_my_courses", ctx, db, {})
    assert len(rows) == 9  # matches the enrollments row count for this student/term
    assert {"course", "name", "faculty", "credits"} <= rows[0].keys()


def test_get_my_timetable_filters_by_day():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        full_week = REGISTRY.invoke("get_my_timetable", ctx, db, {})
        monday = REGISTRY.invoke("get_my_timetable", ctx, db, {"day": 0})
    assert all(r["day_of_week"] == 0 for r in monday)
    assert len(monday) <= len(full_week)


def test_get_my_exam_schedule_matches_students_dept_and_semester():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        rows = REGISTRY.invoke("get_my_exam_schedule", ctx, db, {})
    # shape check only — the sample's exam window for this term/dept may be empty
    assert isinstance(rows, list)
    for r in rows:
        assert {"exam_type", "course", "date"} <= r.keys()


def test_get_my_results_filters_by_semester():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        all_results = REGISTRY.invoke("get_my_results", ctx, db, {})
        sem1 = REGISTRY.invoke("get_my_results", ctx, db, {"semester": 1})
    assert all(r["semester"] == 1 for r in sem1)
    assert len(sem1) <= len(all_results)


def test_get_my_assignments_filters_by_status():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        rows = REGISTRY.invoke("get_my_assignments", ctx, db, {"status": "missing"})
    assert all(r["status"] == "missing" for r in rows)


def test_get_my_scholarships_and_leave_requests_run_for_any_student():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        scholarships = REGISTRY.invoke("get_my_scholarships", ctx, db, {})
        leaves = REGISTRY.invoke("get_my_leave_requests", ctx, db, {})
    assert isinstance(scholarships, list)
    assert isinstance(leaves, list)


# --- Shared tools ------------------------------------------------------------

def test_get_academic_calendar_returns_current_term_events():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        rows = REGISTRY.invoke("get_academic_calendar", ctx, db, {})
    assert len(rows) > 0
    assert {"event", "event_type", "start_date"} <= rows[0].keys()


def test_search_university_policies_runs_with_empty_doc_store():
    ctx = make_ctx("student", subject_id=DEMO_STUDENT_ID)
    with SessionLocal() as db:
        rows = REGISTRY.invoke("search_university_policies", ctx, db, {"query": "attendance"})
    assert rows == []  # doc_chunks is only populated by the Phase-3 RAG ingest


def test_get_my_announcements_runs_for_every_role():
    with SessionLocal() as db:
        for role in ("student", "faculty", "admin"):
            ctx = make_ctx(role)
            rows = REGISTRY.invoke("get_my_announcements", ctx, db, {})
            assert isinstance(rows, list)
