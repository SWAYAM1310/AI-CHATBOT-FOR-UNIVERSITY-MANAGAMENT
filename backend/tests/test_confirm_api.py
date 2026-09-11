"""Phase 2 step 7c — POST /api/chat/confirm, the second half of an action turn.

Scripted provider as in test_chat_api; the DB is the real one and every row an
action writes is removed again by the `undo` fixture.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.ai.tools import confirm
from app.api import chat as chat_api
from app.db.session import SessionLocal
from app.main import app
from app.models import LeaveRequest, Message, User
from tests.test_chat_api import _headers, _message_rows
from tests.test_orchestrator import ScriptedProvider, answer, plan, route

client = TestClient(app)
STUDENT = "student:17"


@pytest.fixture()
def scripted():
    provider = ScriptedProvider()
    app.dependency_overrides[chat_api.get_provider] = lambda: provider
    try:
        yield provider
    finally:
        app.dependency_overrides.pop(chat_api.get_provider, None)


@pytest.fixture()
def undo():
    with SessionLocal() as s:
        high = s.scalar(select(func.coalesce(func.max(LeaveRequest.id), 0)))
    yield
    with SessionLocal() as s:
        s.execute(delete(LeaveRequest).where(LeaveRequest.id > high))
        s.commit()


def _user_id(subject_ref: str) -> int:
    with SessionLocal() as db:
        return db.scalars(select(User.id).where(User.subject_ref == subject_ref)).one()


def _leave_args(offset: int = 40) -> dict:
    start = date.today() + timedelta(days=offset)
    return {"from_date": start.isoformat(), "to_date": (start + timedelta(days=1)).isoformat(), "reason": "cousin's wedding"}


def _leave_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(LeaveRequest.id)))


# --- the happy round trip ------------------------------------------------------

def test_action_turn_stops_on_a_card_and_confirm_executes_it(scripted, undo):
    scripted.responses += [route(tools=["apply_for_leave"]), plan(("apply_for_leave", _leave_args()))]
    before = _leave_count()

    r = client.post("/api/chat", json={"message": "apply for leave for my cousin's wedding"}, headers=_headers())
    assert r.status_code == 200, r.text
    turn = r.json()
    assert turn["path"] == "confirm" and turn["text"] == ""
    card = turn["cards"][0]
    assert card["type"] == "confirm" and card["tool"] == "apply_for_leave"
    assert card["preview"]["days"] == 2 and card["token"]
    assert len(scripted.calls) == 2  # Call A + Call B, no Call C
    assert _leave_count() == before  # nothing written yet

    # the card survives a reload of the transcript
    transcript = client.get(f"/api/chat/{turn['conversation_id']}", headers=_headers()).json()
    assert transcript[-1]["cards"][0]["token"] == card["token"]

    r = client.post(
        "/api/chat/confirm",
        json={"token": card["token"], "conversation_id": turn["conversation_id"]},
        headers=_headers(),
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["tool"] == "apply_for_leave" and out["result"]["done"] is True
    assert out["text"].startswith("Leave application #")
    assert _leave_count() == before + 1
    assert len(scripted.calls) == 2  # confirm never talks to the model

    rows = _message_rows(turn["conversation_id"])
    assert [m.role for m in rows] == ["user", "assistant", "assistant"]
    assert rows[-1].id == out["message_id"] and rows[-1].content == out["text"]
    assert rows[-1].tool_calls[0]["executed"] is True

    # single use
    r = client.post("/api/chat/confirm", json={"token": card["token"]}, headers=_headers())
    assert r.status_code == 409
    assert _leave_count() == before + 1


def test_confirm_without_a_conversation_still_executes(undo):
    tok = confirm.sign(user_id=_user_id(STUDENT), tool="apply_for_leave", args=_leave_args(50))
    r = client.post("/api/chat/confirm", json={"token": tok}, headers=_headers())
    assert r.status_code == 200, r.text
    assert r.json()["conversation_id"] is None and r.json()["message_id"] is None


# --- what a token cannot do ----------------------------------------------------

def test_someone_elses_token_and_garbage_are_400():
    other = _user_id("student:3")
    tok = confirm.sign(user_id=other, tool="apply_for_leave", args=_leave_args())
    assert client.post("/api/chat/confirm", json={"token": tok}, headers=_headers()).status_code == 400
    assert client.post("/api/chat/confirm", json={"token": "nope.nope"}, headers=_headers()).status_code == 400
    assert client.post("/api/chat/confirm", json={"token": tok}).status_code in (401, 403)


def test_expired_token_is_410():
    tok = confirm.sign(user_id=_user_id(STUDENT), tool="apply_for_leave", args=_leave_args(), now=time.time() - 3600)
    r = client.post("/api/chat/confirm", json={"token": tok}, headers=_headers())
    assert r.status_code == 410


def test_rbac_is_rechecked_at_execution_time():
    """A validly signed token for a tool the caller's role may not use is denied, not run."""
    tok = confirm.sign(
        user_id=_user_id(STUDENT), tool="mark_attendance", args={"course_code": "24CS201T", "date": date.today().isoformat()}
    )
    r = client.post("/api/chat/confirm", json={"token": tok}, headers=_headers())
    assert r.status_code == 403


def test_token_for_a_read_tool_is_400():
    tok = confirm.sign(user_id=_user_id(STUDENT), tool="get_my_fees", args={})
    assert client.post("/api/chat/confirm", json={"token": tok}, headers=_headers()).status_code == 400


def test_stale_facts_fail_the_second_validation_with_409():
    """The token freezes the arguments, not the world: a now-invalid action is refused, not forced."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tok = confirm.sign(
        user_id=_user_id(STUDENT), tool="apply_for_leave",
        args={"from_date": yesterday, "to_date": yesterday, "reason": "late"},
    )
    before = _leave_count()
    r = client.post("/api/chat/confirm", json={"token": tok}, headers=_headers())
    assert r.status_code == 409
    assert "past" in r.json()["detail"]
    assert _leave_count() == before
    # the token was not consumed by the failure, and is still refused for the same reason
    assert client.post("/api/chat/confirm", json={"token": tok}, headers=_headers()).status_code == 409


def test_other_users_conversation_cannot_be_used_to_file_the_outcome(scripted):
    scripted.responses += [route(intent="smalltalk"), answer("hi")]
    theirs = client.post("/api/chat", json={"message": "hi"}, headers=_headers(subject_ref=None, role="faculty")).json()
    tok = confirm.sign(user_id=_user_id(STUDENT), tool="apply_for_leave", args=_leave_args(60))
    r = client.post("/api/chat/confirm", json={"token": tok, "conversation_id": theirs["conversation_id"]}, headers=_headers())
    assert r.status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Message.id)).where(Message.conversation_id == theirs["conversation_id"])) == 2
