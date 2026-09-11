"""Phase 2 step 7c — action tools and confirm tokens (plan.md §6 "Action tools", §7).

Real DB, no LLM. Everything an action writes is undone by the `undo` fixture, so
the sample dataset the other test modules rely on is unchanged afterwards.

Cast: student 17 (CP, roll 25BCP017); faculty 2 teaches 24CS201T; faculty 4 is
HOD of CP, faculty 5 HOD of IT; leave request #4 is a pending CP request.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.ai.tools import action_tools, confirm
from app.ai.tools.registry import REGISTRY, ToolDenied
from app.ai.tools.schema import function_schema
from app.auth.context import Role
from app.auth.security import verify_password
from app.db.session import SessionLocal
from app.models import (
    Announcement,
    Assessment,
    AttendanceRecord,
    AttendanceSession,
    AuditLog,
    DocumentRequest,
    LeaveRequest,
    Mark,
    Student,
    User,
)
from tests.conftest import make_ctx

DBMS = "24CS201T"
TEACHES_DBMS = 2
NOT_DBMS = 1
HOD_CP, HOD_IT = 4, 5
PENDING_CP_LEAVE = 4  # student 21, 25BCP021

ACTIONS = {
    "student": {"apply_for_leave", "request_document"},
    "faculty": {"mark_attendance", "enter_marks", "post_announcement", "decide_leave_request"},
    "admin": {"publish_notice", "manage_user"},
}
APPEND_ONLY = (LeaveRequest, DocumentRequest, Announcement, AttendanceRecord, AttendanceSession, Mark)


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def undo():
    """Delete every row an action inserted during the test (children before parents)."""
    with SessionLocal() as s:
        high = {m: s.scalar(select(func.coalesce(func.max(m.id), 0))) for m in APPEND_ONLY}
    yield
    with SessionLocal() as s:
        for m in APPEND_ONLY:
            s.execute(delete(m).where(m.id > high[m]))
        s.commit()


def tomorrow(days: int = 1) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def leave_args(**over):
    return {"from_date": tomorrow(30), "to_date": tomorrow(31), "reason": "family function", **over}


def last_audit(db) -> AuditLog:
    return db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).one()


# --- registry: what makes a tool an action --------------------------------------

def test_exactly_the_eight_action_tools_are_flagged_and_role_scoped():
    flagged = {t.name for t in REGISTRY.all() if t.action}
    assert flagged == ACTIONS["student"] | ACTIONS["faculty"] | ACTIONS["admin"]
    for role, names in ACTIONS.items():
        visible = {t["name"] for t in REGISTRY.index_for(Role(role))}
        assert names <= visible
        others = set().union(*(v for k, v in ACTIONS.items() if k != role))
        assert not others & visible


@pytest.mark.parametrize("name", sorted(set().union(*ACTIONS.values())))
def test_confirmed_is_never_in_the_schema_the_model_sees(name):
    params = function_schema(REGISTRY.get(name))["function"]["parameters"]
    assert "confirmed" not in params["properties"]


def test_a_model_supplied_confirmed_flag_is_dropped(db, undo):
    """The only route to execution is the signed token, not an argument."""
    student = make_ctx("student", 17)
    before = db.scalar(select(func.count(LeaveRequest.id)))
    out = REGISTRY.invoke("apply_for_leave", student, db, {**leave_args(), "confirmed": True})
    assert out["needs_confirmation"] is True
    assert db.scalar(select(func.count(LeaveRequest.id))) == before
    assert last_audit(db).decision == "allowed"


def test_confirmed_on_a_read_tool_is_refused(db):
    with pytest.raises(ValueError):
        REGISTRY.invoke("get_my_fees", make_ctx("student", 17), db, {}, confirmed=True)


def test_execution_is_audited_as_confirmed(db, undo):
    student = make_ctx("student", 17)
    out = REGISTRY.invoke("apply_for_leave", student, db, leave_args(), confirmed=True)
    assert out["done"] is True
    assert last_audit(db).decision == "confirmed"


@pytest.mark.parametrize("role,name", [(r, n) for r, ns in ACTIONS.items() for n in sorted(ns)])
def test_other_roles_are_denied_even_with_confirmed(role, name, db):
    other = {"student": "faculty", "faculty": "admin", "admin": "student"}[role]
    with pytest.raises(ToolDenied):
        REGISTRY.invoke(name, make_ctx(other), db, {}, confirmed=True)
    assert last_audit(db).decision == "denied"


# --- the token ----------------------------------------------------------------

def test_token_round_trips_tool_and_args_for_the_same_user():
    args = {"to_date": "2026-10-02", "from_date": "2026-10-01", "reason": "x"}
    tok = confirm.sign(user_id=7, tool="apply_for_leave", args=args)
    assert confirm.verify(tok, user_id=7) == ("apply_for_leave", args)


def test_token_is_bound_to_user_and_tamper_evident():
    tok = confirm.sign(user_id=7, tool="apply_for_leave", args={"a": 1})
    with pytest.raises(confirm.TokenInvalid):
        confirm.verify(tok, user_id=8)
    body, _, sig = tok.partition(".")
    with pytest.raises(confirm.TokenInvalid):
        confirm.verify(f"{body}x.{sig}", user_id=7)
    with pytest.raises(confirm.TokenInvalid):
        confirm.verify("garbage", user_id=7)


def test_token_expires_after_the_ttl_and_is_single_use():
    issued = time.time()
    tok = confirm.sign(user_id=7, tool="t", args={}, now=issued)
    confirm.verify(tok, user_id=7, now=issued + 299)
    with pytest.raises(confirm.TokenExpired):
        confirm.verify(tok, user_id=7, now=issued + 300)

    tok2 = confirm.sign(user_id=7, tool="t", args={})
    confirm.verify(tok2, user_id=7)
    confirm.consume(tok2)
    with pytest.raises(confirm.TokenUsed):
        confirm.verify(tok2, user_id=7)


def test_preview_pass_writes_nothing(db, undo):
    """Every action, given valid input, must stop at the preview without touching a table."""
    counts = lambda: {m.__tablename__: db.scalar(select(func.count(m.id))) for m in APPEND_ONLY}  # noqa: E731
    before = counts()
    calls = [
        ("student", 17, "apply_for_leave", leave_args()),
        ("student", 17, "request_document", {"doc_type": "bus pass"}),
        ("faculty", TEACHES_DBMS, "mark_attendance", {"course_code": DBMS, "date": date.today().isoformat()}),
        ("faculty", TEACHES_DBMS, "enter_marks", {"course_code": DBMS, "assessment": "Quiz-1", "marks": {"25BCP017": 5}}),
        ("faculty", TEACHES_DBMS, "post_announcement", {"course_code": DBMS, "title": "t", "body": "b"}),
        ("faculty", HOD_CP, "decide_leave_request", {"leave_request_id": PENDING_CP_LEAVE, "decision": "approve"}),
        ("admin", None, "publish_notice", {"title": "t", "body": "b"}),
        ("admin", None, "manage_user", {"email": "25bcp017@sot.pdpu.ac.in", "action": "deactivate"}),
    ]
    for role, sid, name, args in calls:
        out = REGISTRY.invoke(name, make_ctx(role, sid), db, args)
        assert out.get("needs_confirmation") is True, (name, out)
        assert out["preview"]["summary"] and out["token"]
        assert confirm.verify(out["token"], user_id=make_ctx(role, sid).user_id)[0] == name
    db.commit()
    assert counts() == before
    assert db.scalar(select(LeaveRequest.status).where(LeaveRequest.id == PENDING_CP_LEAVE)) == "pending"


# --- student ------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad,needle",
    [
        (leave_args(from_date="yesterday"), "YYYY-MM-DD"),
        (leave_args(from_date=tomorrow(-1), to_date=tomorrow(1)), "past"),
        (leave_args(from_date=tomorrow(5), to_date=tomorrow(4)), "before"),
        (leave_args(to_date=tomorrow(30 + action_tools.MAX_LEAVE_DAYS)), "at most"),
        (leave_args(reason="  "), "reason"),
    ],
)
def test_apply_for_leave_validates(bad, needle, db):
    out = REGISTRY.invoke("apply_for_leave", make_ctx("student", 17), db, bad)
    assert needle in out["error"]


def test_apply_for_leave_previews_then_writes_and_refuses_a_duplicate(db, undo):
    student = make_ctx("student", 17)
    args = leave_args()
    first = REGISTRY.invoke("apply_for_leave", student, db, args)
    assert first["preview"]["days"] == 2 and first["preview"]["approver"]  # CP has an HOD

    done = REGISTRY.invoke("apply_for_leave", student, db, args, confirmed=True)
    assert done["done"] and "pending approval from" in done["message"]
    row = db.get(LeaveRequest, done["leave_request_id"])
    assert (row.student_id, row.roll_no, row.status) == (17, "25BCP017", "pending")

    # the same token replayed after a restart would land here: the overlap check refuses it
    again = REGISTRY.invoke("apply_for_leave", student, db, args, confirmed=True)
    assert f"#{row.id}" in again["error"]


def test_request_document_matches_loosely_and_blocks_a_duplicate_open_request(db, undo):
    student = make_ctx("student", 17)
    assert "allowed:" in REGISTRY.invoke("request_document", student, db, {"doc_type": "passport"})["error"]
    out = REGISTRY.invoke("request_document", student, db, {"doc_type": "transcript", "purpose": "MS application"})
    assert out["preview"]["doc_type"] == "Official Transcript"
    done = REGISTRY.invoke(
        "request_document", student, db, {"doc_type": "Official Transcript", "purpose": "MS application"}, confirmed=True
    )
    assert db.get(DocumentRequest, done["document_request_id"]).status == "processing"
    again = REGISTRY.invoke("request_document", student, db, {"doc_type": "transcript"})
    assert "already have an open request" in again["error"]


# --- faculty ------------------------------------------------------------------

def test_mark_attendance_is_gated_and_validated(db):
    other = make_ctx("faculty", NOT_DBMS)
    teacher = make_ctx("faculty", TEACHES_DBMS)
    today = date.today().isoformat()
    assert "do not teach" in REGISTRY.invoke("mark_attendance", other, db, {"course_code": DBMS, "date": today})["error"]
    assert "future" in REGISTRY.invoke("mark_attendance", teacher, db, {"course_code": DBMS, "date": tomorrow()})["error"]
    out = REGISTRY.invoke("mark_attendance", teacher, db, {"course_code": DBMS, "date": today, "absent_roll_nos": ["99XXX999"]})
    assert "not enrolled" in out["error"]
    taken = db.scalar(select(AttendanceSession.session_date).where(AttendanceSession.subject_code == DBMS).limit(1))
    out = REGISTRY.invoke("mark_attendance", teacher, db, {"course_code": DBMS, "date": taken.isoformat()})
    assert "already recorded" in out["error"]


def test_mark_attendance_writes_a_session_and_a_record_per_enrolled_student(db, undo):
    teacher = make_ctx("faculty", TEACHES_DBMS)
    before = REGISTRY.invoke("get_course_attendance_summary", teacher, db, {"course_code": DBMS})
    args = {"course_code": DBMS, "date": date.today().isoformat(), "absent_roll_nos": "25bcp017, 25BCP003"}
    preview = REGISTRY.invoke("mark_attendance", teacher, db, args)["preview"]
    assert preview["absent_roll_nos"] == ["25BCP003", "25BCP017"]
    assert preview["present"] + 2 == before["students"]

    done = REGISTRY.invoke("mark_attendance", teacher, db, args, confirmed=True)
    records = db.scalars(select(AttendanceRecord).where(AttendanceRecord.session_id == done["session_id"])).all()
    assert len(records) == before["students"]
    assert sum(r.status == "absent" for r in records) == 2
    session = db.get(AttendanceSession, done["session_id"])
    assert session.marked_by == TEACHES_DBMS
    after = REGISTRY.invoke("get_course_attendance_summary", teacher, db, {"course_code": DBMS})
    assert after["sessions_held"] == before["sessions_held"] + 1


def test_enter_marks_validates_assessment_roster_and_range(db):
    teacher = make_ctx("faculty", TEACHES_DBMS)
    base = {"course_code": DBMS, "marks": {"25BCP017": 5}}
    out = REGISTRY.invoke("enter_marks", teacher, db, {**base, "assessment": "Viva"})
    assert "no assessment" in out["error"] and "Quiz-1" in out["error"]
    out = REGISTRY.invoke("enter_marks", teacher, db, {**base, "assessment": "Quiz-1", "marks": {"99XXX999": 5}})
    assert "not enrolled" in out["error"]
    out = REGISTRY.invoke("enter_marks", teacher, db, {**base, "assessment": "Quiz-1", "marks": {"25BCP017": 1e6}})
    assert "outside" in out["error"]
    out = REGISTRY.invoke("enter_marks", teacher, db, {**base, "assessment": "Quiz-1", "marks": {"25BCP017": "lots"}})
    assert "not a number" in out["error"]


def test_enter_marks_upserts_and_the_summary_reflects_it(db, undo):
    teacher = make_ctx("faculty", TEACHES_DBMS)
    quiz = db.scalars(select(Assessment).where(Assessment.subject_code == DBMS, Assessment.type == "Quiz-1")).first()
    mark = db.scalars(select(Mark).where(Mark.assessment_id == quiz.id).limit(1)).one()
    original = (mark.student_id, mark.score, mark.is_absent, mark.graded_on)
    roll = db.scalar(select(Student.roll_no).where(Student.id == mark.student_id))
    try:
        args = {"course_code": DBMS, "assessment": "quiz-1", "marks": [{"roll_no": roll, "score": 1}]}
        preview = REGISTRY.invoke("enter_marks", teacher, db, args)["preview"]
        assert preview["assessment"] == "Quiz-1" and preview["max_marks"] >= 1
        done = REGISTRY.invoke("enter_marks", teacher, db, args, confirmed=True)
        assert (done["inserted"], done["updated"]) == (0, 1)
        db.refresh(mark)
        assert float(mark.score) == 1.0 and mark.is_absent is False
        rows = REGISTRY.invoke("get_course_marks_summary", teacher, db, {"course_code": DBMS, "assessment_type": "Quiz-1"})
        assert rows[0]["lowest"] <= 1.0
    finally:
        mark.student_id, mark.score, mark.is_absent, mark.graded_on = original
        db.commit()


def test_post_announcement_reaches_an_enrolled_student(db, undo):
    teacher = make_ctx("faculty", TEACHES_DBMS)
    assert "do not teach" in REGISTRY.invoke(
        "post_announcement", make_ctx("faculty", NOT_DBMS), db, {"course_code": DBMS, "title": "t", "body": "b"}
    )["error"]
    assert "required" in REGISTRY.invoke("post_announcement", teacher, db, {"course_code": DBMS, "title": "t", "body": " "})["error"]
    args = {"course_code": DBMS, "title": "Quiz-2 moved to Friday", "body": "Same syllabus, same room."}
    done = REGISTRY.invoke("post_announcement", teacher, db, args, confirmed=True)
    db.commit()
    row = db.get(Announcement, done["announcement_id"])
    assert (row.scope, row.scope_ref, row.audience_roles, row.author_user_id) == ("course", DBMS, "student", teacher.user_id)
    seen = REGISTRY.invoke("get_my_announcements", make_ctx("student", 17), db)
    assert "Quiz-2 moved to Friday" in {a["title"] for a in seen}


def test_leave_decisions_belong_to_the_students_own_hod(db):
    args = {"leave_request_id": PENDING_CP_LEAVE, "decision": "approve"}
    assert "head of department" in REGISTRY.invoke("decide_leave_request", make_ctx("faculty", TEACHES_DBMS), db, args)["error"]
    assert "your department" in REGISTRY.invoke("decide_leave_request", make_ctx("faculty", HOD_IT), db, args)["error"]
    assert "approve" in REGISTRY.invoke("decide_leave_request", make_ctx("faculty", HOD_CP), db, {**args, "decision": "maybe"})["error"]
    assert REGISTRY.invoke("list_pending_leave_requests", make_ctx("faculty", TEACHES_DBMS), db) == []
    pending = REGISTRY.invoke("list_pending_leave_requests", make_ctx("faculty", HOD_CP), db)
    assert PENDING_CP_LEAVE in {r["leave_request_id"] for r in pending}
    assert PENDING_CP_LEAVE not in {
        r["leave_request_id"] for r in REGISTRY.invoke("list_pending_leave_requests", make_ctx("faculty", HOD_IT), db)
    }


def test_decide_leave_request_approves_once(db):
    hod = make_ctx("faculty", HOD_CP)
    args = {"leave_request_id": PENDING_CP_LEAVE, "decision": "approved"}
    preview = REGISTRY.invoke("decide_leave_request", hod, db, args)["preview"]
    assert preview["roll_no"] == "25BCP021" and preview["decision"] == "approve"
    try:
        done = REGISTRY.invoke("decide_leave_request", hod, db, args, confirmed=True)
        assert done["status"] == "approved"
        row = db.get(LeaveRequest, PENDING_CP_LEAVE)
        assert (row.status, row.decided_by, row.decided_on) == ("approved", HOD_CP, date.today())
        assert "already approved" in REGISTRY.invoke("decide_leave_request", hod, db, args)["error"]
    finally:
        row = db.get(LeaveRequest, PENDING_CP_LEAVE)
        row.status, row.decided_by, row.decided_on = "pending", None, None
        db.commit()


# --- admin --------------------------------------------------------------------

def test_publish_notice_validates_audience_and_department_then_posts(db, undo):
    admin = make_ctx("admin")
    assert "audience" in REGISTRY.invoke("publish_notice", admin, db, {"title": "t", "body": "b", "audience": "everyone"})["error"]
    assert "no department" in REGISTRY.invoke("publish_notice", admin, db, {"title": "t", "body": "b", "dept": "ZZ"})["error"]
    assert "longer than" in REGISTRY.invoke("publish_notice", admin, db, {"title": "x" * 200, "body": "b"})["error"]
    args = {"title": "Lab closed Monday", "body": "Maintenance.", "audience": "Student", "dept": "cp"}
    preview = REGISTRY.invoke("publish_notice", admin, db, args)["preview"]
    assert (preview["scope"], preview["dept"], preview["audience"]) == ("department", "CP", "student")
    done = REGISTRY.invoke("publish_notice", admin, db, args, confirmed=True)
    db.commit()
    row = db.get(Announcement, done["announcement_id"])
    assert (row.scope, row.scope_ref, row.audience_roles) == ("department", "CP", "student")
    assert "Lab closed Monday" in {a["title"] for a in REGISTRY.invoke("get_my_announcements", make_ctx("student", 17), db)}
    assert "Lab closed Monday" not in {a["title"] for a in REGISTRY.invoke("get_my_announcements", make_ctx("faculty", HOD_CP), db)}


def test_manage_user_deactivates_reactivates_and_resets_a_password(db):
    admin = make_ctx("admin")
    me = db.get(User, admin.user_id)
    assert "own account" in REGISTRY.invoke("manage_user", admin, db, {"email": me.email, "action": "deactivate"})["error"]
    assert "no account" in REGISTRY.invoke("manage_user", admin, db, {"email": "nobody@x", "action": "deactivate"})["error"]
    assert "action must" in REGISTRY.invoke("manage_user", admin, db, {"email": me.email, "action": "delete"})["error"]

    target = db.scalars(select(User).where(User.role == "student").limit(1)).one()
    original_hash = target.password_hash
    try:
        done = REGISTRY.invoke("manage_user", admin, db, {"email": target.email.upper(), "action": "deactivate"}, confirmed=True)
        assert done["is_active"] is False
        db.refresh(target)
        assert target.is_active is False
        assert "already inactive" in REGISTRY.invoke("manage_user", admin, db, {"email": target.email, "action": "deactivate"})["error"]
        REGISTRY.invoke("manage_user", admin, db, {"email": target.email, "action": "activate"}, confirmed=True)
        db.refresh(target)
        assert target.is_active is True

        done = REGISTRY.invoke("manage_user", admin, db, {"email": target.email, "action": "reset_password"}, confirmed=True)
        db.refresh(target)
        assert verify_password(done["temporary_password"], target.password_hash)
        assert not verify_password("uniassist", target.password_hash)
    finally:
        db.refresh(target)
        target.is_active, target.password_hash = True, original_hash
        db.commit()
