"""The three RBAC enforcement layers (plan.md §5 / §12). This suite must stay green."""
from __future__ import annotations

import pytest
from sqlalchemy import desc, select, text

from app.ai.tools.registry import REGISTRY, ToolDenied
from app.auth.context import Role
from app.db.session import SessionLocal
from app.models import AuditLog
from tests.conftest import make_ctx

FACULTY_TOOL = "list_students_below_attendance"
# from data/synthetic/sample: offering of 24CS201T is taught by faculty id 2
TEACHES_DBMS = 2
NOT_DBMS = 1  # faculty id 1 teaches 24CS202T, not 24CS201T


def _last_decision(tool_name: str) -> str:
    with SessionLocal() as db:
        return db.scalars(
            select(AuditLog.decision)
            .where(AuditLog.tool_name == tool_name)
            .order_by(desc(AuditLog.id))
            .limit(1)
        ).one()


# --- Layer 1: tool exposure -------------------------------------------------

def test_faculty_tool_hidden_from_student_index():
    names = {t["name"] for t in REGISTRY.index_for(Role.STUDENT)}
    assert FACULTY_TOOL not in names
    assert "get_my_attendance" in names


def test_student_tools_hidden_from_admin_where_not_shared():
    names = {t["name"] for t in REGISTRY.index_for(Role.ADMIN)}
    assert "get_my_attendance" not in names  # SELF student tool
    assert FACULTY_TOOL in names             # shared faculty/admin tool


# --- Layer 2: execution guard --------------------------------------------

def test_student_invoking_faculty_tool_is_denied_and_audited():
    ctx = make_ctx("student")
    with SessionLocal() as db, pytest.raises(ToolDenied):
        REGISTRY.invoke(FACULTY_TOOL, ctx, db, {"course_code": "24CS201T"})
    assert _last_decision(FACULTY_TOOL) == "denied"


# --- Layer 3: identity args are never trusted --------------------------

def test_student_id_arg_is_stripped_and_returns_own_data():
    ctx = make_ctx("student")
    with SessionLocal() as db:
        own = REGISTRY.invoke("get_my_attendance", ctx, db, {})
        spoofed = REGISTRY.invoke(
            "get_my_attendance", ctx, db, {"student_id": 999999, "roll_no": "25BCP099"}
        )
    assert own == spoofed
    assert _last_decision("get_my_attendance") == "arg_stripped"


def test_admin_may_pass_identity_args_without_stripping():
    ctx = make_ctx("admin")
    with SessionLocal() as db:
        REGISTRY.invoke(FACULTY_TOOL, ctx, db, {"course_code": "24CS201T", "faculty_id": 2})
    assert _last_decision(FACULTY_TOOL) == "allowed"


# --- Scope: faculty OWN_COURSES ---------------------------------------

def test_faculty_sees_own_course_roster():
    ctx = make_ctx("faculty", subject_id=TEACHES_DBMS)
    with SessionLocal() as db:
        rows = REGISTRY.invoke("list_course_students", ctx, db, {"course_code": "24CS201T"})
    assert len(rows) > 0


def test_faculty_gets_nothing_for_a_course_they_dont_teach():
    ctx = make_ctx("faculty", subject_id=NOT_DBMS)
    with SessionLocal() as db:
        rows = REGISTRY.invoke("list_course_students", ctx, db, {"course_code": "24CS201T"})
    assert rows == []
