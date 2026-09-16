"""Email outbox: queueing, redirect, the recipient guard, idempotency, and the
leave tools' wiring into it (app/notify/, app/ai/tools/action_tools.py).

Real DB, no LLM (email_draft_enabled stays off, its own default — the
deterministic template in app/notify/templates.py is what these assert
against), no network (transport is always MemoryTransport or left at the
console default; nothing here ever calls SmtpTransport).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.ai.tools.registry import REGISTRY
from app.config import settings
from app.db.session import SessionLocal
from app.models import EmailOutbox, Faculty, LeaveRequest, Student
from app.notify import mailer
from app.notify.mailer import collecting, flush_outbox, queue_email
from app.notify.templates import leave_applied_subject, leave_decided_subject
from app.notify.transport import MemoryTransport
from tests.conftest import make_ctx

HOD_CP = 4  # faculty 4 is HOD of CP (see tests/test_action_tools.py)
PENDING_CP_LEAVE = 4  # student 21, 25BCP021 — a pending CP leave request


def tomorrow(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def leave_args(**over):
    return {"from_date": tomorrow(40), "to_date": tomorrow(41), "reason": "family function", **over}


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture(autouse=True)
def _email_defaults(monkeypatch):
    """Every test starts from the same known settings; opt into smtp/redirect explicitly."""
    monkeypatch.setattr(settings, "email_mode", "console")
    monkeypatch.setattr(settings, "email_draft_enabled", False)
    monkeypatch.setattr(settings, "email_redirect_to", "")
    monkeypatch.setattr(settings, "email_allowed_domains", "sot.pdpu.ac.in")
    monkeypatch.setattr(settings, "smtp_host", "localhost")


@pytest.fixture()
def undo():
    """Delete every EmailOutbox/LeaveRequest row a test inserted."""
    with SessionLocal() as s:
        high = {
            EmailOutbox: s.scalar(select(func.coalesce(func.max(EmailOutbox.id), 0))),
            LeaveRequest: s.scalar(select(func.coalesce(func.max(LeaveRequest.id), 0))),
        }
    yield
    with SessionLocal() as s:
        s.execute(delete(EmailOutbox).where(EmailOutbox.id > high[EmailOutbox]))
        s.execute(delete(LeaveRequest).where(LeaveRequest.id > high[LeaveRequest]))
        s.commit()


# --- queue_email: redirect, guard, idempotency, off ----------------------------

def test_off_mode_queues_nothing(db):
    settings.email_mode = "off"
    row = queue_email(
        db, idempotency_key="t:off", to_addr="milan.vyas@sot.pdpu.ac.in",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    assert row is None
    db.rollback()


def test_redirect_rewrites_recipient_and_preserves_original(db, undo):
    settings.email_mode = "console"
    settings.email_redirect_to = "demo-inbox@example.com"
    row = queue_email(
        db, idempotency_key="t:redirect", to_addr="milan.vyas@sot.pdpu.ac.in",
        subject="s", body="original body", related_type="leave_request", related_id=1,
    )
    db.commit()
    assert row.to_addr == "demo-inbox@example.com"
    assert row.intended_to == "milan.vyas@sot.pdpu.ac.in"
    assert row.status == "queued"
    assert "milan.vyas@sot.pdpu.ac.in" in row.body  # the banner names the true recipient
    assert row.body.endswith("original body")


def test_stranger_domain_is_suppressed_on_a_real_host_with_no_redirect(db, undo):
    settings.smtp_host = "smtp.gmail.com"  # not a local sandbox
    row = queue_email(
        db, idempotency_key="t:stranger", to_addr="random.person@gmail.com",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    db.commit()
    assert row.status == "suppressed"
    assert row.to_addr == "random.person@gmail.com"  # unrewritten: never sent, so no redirect needed
    assert "not allowlisted" in row.error


def test_local_sandbox_host_allows_any_domain_without_redirect(db, undo):
    settings.smtp_host = "localhost"  # Mailpit: nothing leaves the machine
    row = queue_email(
        db, idempotency_key="t:local", to_addr="random.person@gmail.com",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    db.commit()
    assert row.status == "queued"


def test_allowlisted_domain_sends_even_on_a_real_host(db, undo):
    settings.smtp_host = "smtp.gmail.com"
    row = queue_email(
        db, idempotency_key="t:allowlisted", to_addr="milan.vyas@sot.pdpu.ac.in",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    db.commit()
    assert row.status == "queued"


def test_replayed_idempotency_key_does_not_double_queue(db, undo):
    first = queue_email(
        db, idempotency_key="t:dup", to_addr="milan.vyas@sot.pdpu.ac.in",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    db.commit()
    again = queue_email(
        db, idempotency_key="t:dup", to_addr="milan.vyas@sot.pdpu.ac.in",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    db.commit()
    assert first is not None
    assert again is None
    assert db.scalar(select(func.count(EmailOutbox.id)).where(EmailOutbox.idempotency_key == "t:dup")) == 1


def test_rolled_back_transaction_never_leaves_a_queued_row(undo):
    before = None
    with SessionLocal() as s:
        before = s.scalar(select(func.count(EmailOutbox.id)))
        queue_email(
            s, idempotency_key="t:rollback", to_addr="milan.vyas@sot.pdpu.ac.in",
            subject="s", body="b", related_type="leave_request", related_id=1,
        )
        s.rollback()  # the caller's transaction fails for an unrelated reason
    with SessionLocal() as s:
        after = s.scalar(select(func.count(EmailOutbox.id)))
    assert after == before


# --- flush_outbox: actually sends, marks status, never raises -------------------

def test_flush_outbox_sends_via_transport_and_marks_sent(db, undo, monkeypatch):
    transport = MemoryTransport()
    monkeypatch.setattr(mailer, "get_transport", lambda: transport)
    settings.email_redirect_to = "demo-inbox@example.com"
    row = queue_email(
        db, idempotency_key="t:flush", to_addr="milan.vyas@sot.pdpu.ac.in",
        subject="hello", body="body text", related_type="leave_request", related_id=1,
    )
    db.commit()
    flush_outbox(db, [row])
    assert row.status == "sent"
    assert row.sent_at is not None
    assert row.attempts == 1
    assert len(transport.sent) == 1
    sent = transport.sent[0]
    assert sent["to"] == "demo-inbox@example.com"
    assert sent["headers"]["X-UniAssist-Intended-To"] == "milan.vyas@sot.pdpu.ac.in"


def test_flush_outbox_marks_failed_without_raising(db, undo, monkeypatch):
    class BoomTransport:
        def send(self, **kwargs):
            raise RuntimeError("smtp exploded")

    monkeypatch.setattr(mailer, "get_transport", lambda: BoomTransport())
    row = queue_email(
        db, idempotency_key="t:boom", to_addr="milan.vyas@sot.pdpu.ac.in",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    db.commit()
    flush_outbox(db, [row])  # must not raise
    assert row.status == "failed"
    assert "smtp exploded" in row.error


def test_flush_outbox_skips_suppressed_rows(db, undo, monkeypatch):
    transport = MemoryTransport()
    monkeypatch.setattr(mailer, "get_transport", lambda: transport)
    settings.smtp_host = "smtp.gmail.com"
    row = queue_email(
        db, idempotency_key="t:skip", to_addr="random.person@gmail.com",
        subject="s", body="b", related_type="leave_request", related_id=1,
    )
    db.commit()
    flush_outbox(db, [row])
    assert row.status == "suppressed"  # unchanged: never attempted
    assert transport.sent == []


# --- leave tools: draft freezing, HOD/student wiring ----------------------------

def test_apply_for_leave_preview_freezes_the_body_that_gets_sent(db, undo, monkeypatch):
    transport = MemoryTransport()
    monkeypatch.setattr(mailer, "get_transport", lambda: transport)
    student = make_ctx("student", 17)
    args = leave_args()

    preview = REGISTRY.invoke("apply_for_leave", student, db, args)
    email_preview = preview["preview"]["email_preview"]
    hod = db.get(Faculty, HOD_CP)
    assert email_preview["to"] == hod.university_email
    assert email_preview["subject"] == leave_applied_subject("25BCP017", args["from_date"], args["to_date"])
    assert "25BCP017" in email_preview["body"]

    with collecting() as outbox_rows:
        done = REGISTRY.invoke("apply_for_leave", student, db, args, confirmed=True)
    db.commit()
    flush_outbox(db, outbox_rows)

    assert done["done"] is True
    row = db.scalar(
        select(EmailOutbox).where(
            EmailOutbox.related_type == "leave_request", EmailOutbox.related_id == done["leave_request_id"]
        )
    )
    assert row is not None
    assert row.status == "sent"
    # what was shown at preview time is byte-for-byte what got sent
    assert row.subject == email_preview["subject"]
    assert row.body == email_preview["body"]
    assert row.intended_to == hod.university_email


def test_decide_leave_request_queues_email_to_the_student(db, undo, monkeypatch):
    transport = MemoryTransport()
    monkeypatch.setattr(mailer, "get_transport", lambda: transport)
    hod = make_ctx("faculty", HOD_CP)
    args = {"leave_request_id": PENDING_CP_LEAVE, "decision": "approve"}

    preview = REGISTRY.invoke("decide_leave_request", hod, db, args)
    student = db.scalar(
        select(Student).join(LeaveRequest, LeaveRequest.student_id == Student.id).where(
            LeaveRequest.id == PENDING_CP_LEAVE
        )
    )
    email_preview = preview["preview"]["email_preview"]
    assert email_preview["to"] == student.university_email
    assert email_preview["subject"] == leave_decided_subject(student.roll_no, "approved")

    try:
        with collecting() as outbox_rows:
            done = REGISTRY.invoke("decide_leave_request", hod, db, args, confirmed=True)
        db.commit()
        flush_outbox(db, outbox_rows)

        assert done["status"] == "approved"
        row = db.scalar(
            select(EmailOutbox).where(
                EmailOutbox.related_type == "leave_request", EmailOutbox.related_id == PENDING_CP_LEAVE
            )
        )
        assert row is not None
        assert row.status == "sent"
        assert row.intended_to == student.university_email
    finally:
        row = db.get(LeaveRequest, PENDING_CP_LEAVE)
        row.status, row.decided_by, row.decided_on = "pending", None, None
        db.commit()


def test_no_email_queued_when_recipient_has_no_address(db, undo, monkeypatch):
    """A department with no HOD on file must not crash the leave application —
    it just has nobody to notify (queue_email is skipped, not called with None)."""
    transport = MemoryTransport()
    monkeypatch.setattr(mailer, "get_transport", lambda: transport)
    monkeypatch.setattr("app.ai.tools.action_tools._hod", lambda db, dept_id: None)

    student = make_ctx("student", 17)
    args = leave_args()
    with collecting() as outbox_rows:
        done = REGISTRY.invoke("apply_for_leave", student, db, args, confirmed=True)
    db.commit()
    flush_outbox(db, outbox_rows)

    assert done["done"] is True
    assert outbox_rows == []
    row = db.scalar(
        select(EmailOutbox).where(
            EmailOutbox.related_type == "leave_request", EmailOutbox.related_id == done["leave_request_id"]
        )
    )
    assert row is None
