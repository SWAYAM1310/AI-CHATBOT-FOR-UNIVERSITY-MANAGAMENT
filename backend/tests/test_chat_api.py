"""Phase 2 step 5 — POST /api/chat.

The LLM is the scripted provider from the orchestrator tests, injected through
FastAPI's dependency override, so the whole HTTP -> JWT -> AuthContext ->
orchestrator -> tools -> persistence path runs offline against the real DB.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.providers.base import ProviderError, ProviderNotConfigured, ProviderRateLimited
from app.api import chat as chat_api
from app.db.session import SessionLocal
from app.main import app
from app.models import Conversation, Message, User
from tests.test_orchestrator import ScriptedProvider, answer, route

client = TestClient(app)
DEV_PW = "uniassist"
DEMO_STUDENT_EMAIL_SUBJECT = "student:17"  # roll 25BCP017, same as the orchestrator tests


def _token(subject_ref: str | None = None, role: str = "student") -> str:
    with SessionLocal() as db:
        q = select(User.email).where(User.role == role)
        if subject_ref:
            q = q.where(User.subject_ref == subject_ref)
        email = db.scalars(q.limit(1)).one()
    r = client.post("/api/auth/login", json={"email": email, "password": DEV_PW})
    return r.json()["access_token"]


def _headers(subject_ref: str | None = DEMO_STUDENT_EMAIL_SUBJECT, role: str = "student") -> dict:
    return {"Authorization": f"Bearer {_token(subject_ref, role)}"}


class ExplodingProvider:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def chat(self, **_kwargs):
        raise self.exc


@pytest.fixture()
def scripted():
    """Install a scripted provider for one test; the test fills its queue."""
    provider = ScriptedProvider()
    app.dependency_overrides[chat_api.get_provider] = lambda: provider
    try:
        yield provider
    finally:
        app.dependency_overrides.pop(chat_api.get_provider, None)


def _use(provider) -> None:
    app.dependency_overrides[chat_api.get_provider] = lambda: provider


def _message_rows(conversation_id: int) -> list[Message]:
    with SessionLocal() as db:
        return db.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        ).all()


# --- happy path --------------------------------------------------------------

def test_first_message_creates_conversation_and_persists_both_rows(scripted):
    scripted.responses += [
        route(tools=["get_my_attendance"]),
        # no Call B: one candidate with no required args is the fast path
        answer("You are at 68% in 24CS201T.", tokens=(400, 80)),
    ]
    r = client.post("/api/chat", json={"message": "what's my attendance?"}, headers=_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "You are at 68% in 24CS201T."
    assert body["path"] == "fast"
    assert body["cards"] == [] and body["citations"] == []
    # Call A + Call C usage summed into the one assistant row
    assert body["usage"] == {"tokens_in": 520, "tokens_out": 110}
    assert body["queued_seconds"] == 0

    with SessionLocal() as db:
        convo = db.get(Conversation, body["conversation_id"])
    assert convo.title == "what's my attendance?"

    rows = _message_rows(body["conversation_id"])
    assert [m.role for m in rows] == ["user", "assistant"]
    assert rows[0].content == "what's my attendance?"
    assert rows[1].id == body["message_id"]
    assert (rows[1].tokens_in, rows[1].tokens_out) == (520, 110)
    assert rows[1].tool_calls[0]["name"] == "get_my_attendance"
    assert rows[1].tool_calls[0]["ok"] is True


def test_conversation_owner_is_the_caller_not_a_request_field(scripted):
    scripted.responses += [route(intent="smalltalk"), answer("Hi!")]
    r = client.post("/api/chat", json={"message": "hello"}, headers=_headers())
    with SessionLocal() as db:
        convo = db.get(Conversation, r.json()["conversation_id"])
        owner = db.get(User, convo.user_id)
    assert owner.subject_ref == DEMO_STUDENT_EMAIL_SUBJECT


def test_second_message_continues_and_replays_history(scripted):
    scripted.responses += [route(intent="smalltalk"), answer("Hi Aarav!")]
    first = client.post("/api/chat", json={"message": "hi"}, headers=_headers()).json()
    cid = first["conversation_id"]

    scripted.calls.clear()
    scripted.responses += [route(intent="smalltalk"), answer("Still here.")]
    r = client.post("/api/chat", json={"message": "you there?", "conversation_id": cid}, headers=_headers())
    assert r.status_code == 200
    assert r.json()["conversation_id"] == cid

    # Call A of the second turn saw the stored pair before the new question
    call_a = scripted.calls[0]["messages"]
    assert [m["content"] for m in call_a] == ["hi", "Hi Aarav!", "you there?"]

    assert [m.role for m in _message_rows(cid)] == ["user", "assistant", "user", "assistant"]


def test_title_is_truncated_to_the_first_message(scripted):
    scripted.responses += [route(intent="smalltalk"), answer("ok")]
    long = "x" * 500
    r = client.post("/api/chat", json={"message": long}, headers=_headers())
    with SessionLocal() as db:
        convo = db.get(Conversation, r.json()["conversation_id"])
    assert convo.title == "x" * chat_api.TITLE_CHARS


# --- reading back ------------------------------------------------------------

def test_list_and_get_only_show_own_conversations(scripted):
    scripted.responses += [route(intent="smalltalk"), answer("hey")]
    mine = client.post("/api/chat", json={"message": "mine"}, headers=_headers()).json()["conversation_id"]

    other = _headers(subject_ref=None, role="faculty")
    listed = client.get("/api/chat", headers=other).json()
    assert mine not in [c["id"] for c in listed]
    assert client.get(f"/api/chat/{mine}", headers=other).status_code == 404
    assert client.post(
        "/api/chat", json={"message": "hijack", "conversation_id": mine}, headers=other
    ).status_code == 404

    listed = client.get("/api/chat", headers=_headers()).json()
    assert mine in [c["id"] for c in listed]
    transcript = client.get(f"/api/chat/{mine}", headers=_headers()).json()
    assert [m["role"] for m in transcript] == ["user", "assistant"]
    assert transcript[1]["content"] == "hey"
    assert transcript[1]["tokens_in"] == 520  # Call A (120) + Call C (400)


def test_unknown_conversation_is_404(scripted):
    r = client.post("/api/chat", json={"message": "hi", "conversation_id": 999999}, headers=_headers())
    assert r.status_code == 404
    assert scripted.calls == []  # never reached the model


# --- RBAC still holds through HTTP ------------------------------------------

def test_student_cannot_reach_a_faculty_tool_via_chat(scripted):
    """Call A names a faculty tool; the router drops it, no tool runs, Call C still answers."""
    scripted.responses += [
        route(tools=["list_students_below_attendance"]),
        answer("I can't do that for you."),
    ]
    r = client.post("/api/chat", json={"message": "who is below 75%?"}, headers=_headers())
    assert r.status_code == 200
    rows = _message_rows(r.json()["conversation_id"])
    assert rows[1].tool_calls is None  # nothing executed
    assert len(scripted.calls) == 2  # Call B was skipped: there were no candidates


# --- rate limiting and provider failures ------------------------------------

def test_exhausted_429_is_a_503_with_retry_after_and_persists_nothing():
    _use(ExplodingProvider(ProviderRateLimited("429", retry_after=7)))
    try:
        with SessionLocal() as db:
            before = db.scalar(select(Message.id).order_by(Message.id.desc()).limit(1))
        r = client.post("/api/chat", json={"message": "hi"}, headers=_headers())
        assert r.status_code == 503
        assert r.headers["retry-after"] == "7"
        with SessionLocal() as db:
            after = db.scalar(select(Message.id).order_by(Message.id.desc()).limit(1))
        assert after == before  # no orphan user row for the client to duplicate on retry
    finally:
        app.dependency_overrides.pop(chat_api.get_provider, None)


def test_no_key_is_a_503_and_other_provider_errors_are_502():
    try:
        _use(ExplodingProvider(ProviderNotConfigured("no key")))
        assert client.post("/api/chat", json={"message": "hi"}, headers=_headers()).status_code == 503
        _use(ExplodingProvider(ProviderError("boom")))
        assert client.post("/api/chat", json={"message": "hi"}, headers=_headers()).status_code == 502
    finally:
        app.dependency_overrides.pop(chat_api.get_provider, None)


def test_queued_wait_is_reported_not_hidden():
    from app.ai.budget import BudgetedProvider

    scripted = ScriptedProvider(route(intent="smalltalk"), answer("hi"))
    # A tiny TPM bucket forces a wait; the fake sleeper advances the fake clock.
    now = [0.0]
    budgeted = BudgetedProvider(
        scripted, tpm=600, rpm=1000, clock=lambda: now[0],
        sleeper=lambda s: now.__setitem__(0, now[0] + s),
    )
    budgeted.tokens.take(600)  # drain it so the first call has to queue
    _use(budgeted)
    try:
        r = client.post("/api/chat", json={"message": "hi"}, headers=_headers())
        assert r.status_code == 200
        assert r.json()["queued_seconds"] > 0
        assert float(r.headers["x-queued-seconds"]) == r.json()["queued_seconds"]
    finally:
        app.dependency_overrides.pop(chat_api.get_provider, None)


# --- input validation --------------------------------------------------------

def test_requires_token_and_rejects_empty_or_oversized_messages(scripted):
    assert client.post("/api/chat", json={"message": "hi"}).status_code in (401, 403)
    assert client.post("/api/chat", json={"message": ""}, headers=_headers()).status_code == 422
    assert client.post("/api/chat", json={"message": "   "}, headers=_headers()).status_code == 422
    too_long = "x" * (chat_api.MAX_MESSAGE_CHARS + 1)
    assert client.post("/api/chat", json={"message": too_long}, headers=_headers()).status_code == 422
    assert scripted.calls == []
