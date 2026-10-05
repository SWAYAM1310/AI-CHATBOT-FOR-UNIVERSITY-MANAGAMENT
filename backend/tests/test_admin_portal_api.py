"""Phase 7c — fee recording, agentic announcements (recipients, demo cap, background send), admin API.

Real DB, no LLM, no network: the autouse guard in conftest forces the console transport, and tests
that look at what was sent swap in a MemoryTransport. Everything a test writes is removed afterwards.
Cast: student 2 (CP) has a partial fee of 152500 with 71100 paid (fee 4); student 17 (CP, sem 3) is
fully paid; student 57 (26BCP001, CP) is semester 1; the CP department has 44 students and 4 faculty.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.ai.tools.registry import REGISTRY
from app.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import Announcement, EmailOutbox, Fee, Student, User
from app.notify import mailer
from app.notify.announce import (
    Recipient,
    demo_split,
    queue_announcement_emails,
    resolve_recipients,
)
from app.notify.transport import MemoryTransport
from tests.conftest import make_ctx

client = TestClient(app)
DEV_PW = "uniassist"
PARTIAL_FEE = 4  # student 2: due 152500, paid 71100
PAID_FEE = 34  # student 17: paid in full
TERM = "2026-27-ODD"
INBOX = "demo-inbox@example.com"


def _login(subject_ref: str) -> dict:
    with SessionLocal() as db:
        email = db.scalars(select(User.email).where(User.subject_ref == subject_ref)).one()
    r = client.post("/api/auth/login", json={"email": email, "password": DEV_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def adm():
    return _login("admin:1")


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def undo():
    """Remove announcements and outbox rows a test added; put every fee back as it was."""
    with SessionLocal() as s:
        high = {m: s.scalar(select(func.coalesce(func.max(m.id), 0))) for m in (Announcement, EmailOutbox)}
        fees = [(f.id, f.amount_paid, f.status, f.paid_on) for f in s.scalars(select(Fee))]
    yield
    with SessionLocal() as s:
        for m, top in high.items():
            s.execute(delete(m).where(m.id > top))
        for fid, paid, st, on in fees:
            f = s.get(Fee, fid)
            f.amount_paid, f.status, f.paid_on = paid, st, on
        s.commit()


@pytest.fixture()
def mail(monkeypatch):
    """Capture what would really be sent."""
    transport = MemoryTransport()
    monkeypatch.setattr(mailer, "get_transport", lambda: transport)
    return transport


@pytest.fixture()
def demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "email_redirect_to", INBOX)
    monkeypatch.setattr(settings, "email_demo_cap", 4)


NOTICE = {"title": "Lab shift", "body": "The DBMS lab moves to Room B-12 from Monday.", "audience": "student", "dept": "CP"}


def _outbox(announcement_id: int) -> list[EmailOutbox]:
    with SessionLocal() as s:
        return list(s.scalars(select(EmailOutbox).where(EmailOutbox.related_type == "announcement", EmailOutbox.related_id == announcement_id)))


# --- recipients ---------------------------------------------------------------------------------


def test_recipients_follow_audience_department_and_semester(db):
    students = resolve_recipients(db, "student", term=TERM)
    assert len(students) == db.scalar(select(func.count(Student.id)).where(Student.is_active.is_(True)))
    assert {r.role for r in students} == {"student"}

    cp = resolve_recipients(db, "all", term=TERM, dept="CP")
    assert sum(r.role == "student" for r in cp) == 44 and sum(r.role == "faculty" for r in cp) == 4

    sem3 = resolve_recipients(db, "student", term=TERM, semester=3)
    assert sem3 and len(sem3) < len(students)
    assert not any(r.role == "faculty" for r in sem3)

    teaching_sem3 = resolve_recipients(db, "faculty", term=TERM, semester=3)
    assert teaching_sem3 and len(teaching_sem3) < len(resolve_recipients(db, "faculty", term=TERM))

    assert resolve_recipients(db, "student", term=TERM, dept="CP", semester=1) != resolve_recipients(db, "student", term=TERM, dept="CP", semester=3)
    assert len({r.email for r in cp}) == len(cp)


def test_demo_cap_spreads_across_roles_and_holds_the_rest(demo_mode):
    mixed = [Recipient("student", f"S{i}", f"s{i}@x") for i in range(10)] + [Recipient("faculty", f"F{i}", f"f{i}@x") for i in range(5)]
    sent, held = demo_split(mixed)
    assert [r.role for r in sent] == ["student", "faculty", "student", "faculty"]
    assert len(held) == 11 and not set(sent) & set(held) and set(sent) | set(held) == set(mixed)

    only_students = [r for r in mixed if r.role == "student"]
    assert len(demo_split(only_students)[0]) == 4


def test_demo_cap_never_applies_without_a_redirect_or_when_disabled_or_when_small(monkeypatch):
    many = [Recipient("student", f"S{i}", f"s{i}@x") for i in range(30)]
    monkeypatch.setattr(settings, "email_redirect_to", "")
    assert demo_split(many) == (many, [])  # no redirect: Mailpit / allowlisted domain, nobody is "in one inbox"
    monkeypatch.setattr(settings, "email_redirect_to", INBOX)
    monkeypatch.setattr(settings, "email_demo_cap", 0)
    assert demo_split(many) == (many, [])
    monkeypatch.setattr(settings, "email_demo_cap", 40)
    assert demo_split(many) == (many, [])


# --- preview --------------------------------------------------------------------------------------


def test_preview_shows_reach_and_the_email_and_writes_nothing(adm, undo):
    with SessionLocal() as s:
        before = (s.scalar(select(func.count(Announcement.id))), s.scalar(select(func.count(EmailOutbox.id))))
    r = client.post("/api/admin/announcements/preview", headers=adm, json=NOTICE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["emailing"] is True
    assert body["preview"]["recipients_students"] == 44 and body["preview"]["recipients_faculty"] == 0
    assert body["preview"]["emails_to_send"] == 44 and body["preview"]["emails_held"] == 0
    assert body["email"]["subject"] == "[UniAssist] Lab shift"
    assert NOTICE["body"] in body["email"]["body"] and "Students of the CP department" in body["email"]["body"]
    with SessionLocal() as s:
        assert (s.scalar(select(func.count(Announcement.id))), s.scalar(select(func.count(EmailOutbox.id)))) == before


def test_preview_in_demo_mode_says_only_four_will_really_go(adm, demo_mode):
    body = client.post("/api/admin/announcements/preview", headers=adm, json=NOTICE).json()
    assert body["preview"]["emails_to_send"] == 4 and body["preview"]["emails_held"] == 40
    assert "demo mode" in body["email"]["to"] and "44 recipients" in body["email"]["to"]


def test_preview_is_refused_for_bad_input(adm):
    post = lambda **kw: client.post("/api/admin/announcements/preview", headers=adm, json={**NOTICE, **kw})  # noqa: E731
    assert post(dept="ZZ").status_code == 400
    assert post(semester=9).status_code == 422
    assert post(audience="everyone").status_code == 422
    assert post(title="").status_code == 422
    assert post(dept="CP", semester=1, audience="faculty").status_code in (200, 400)  # may legitimately match nobody
    assert client.post("/api/admin/announcements/preview", headers=adm, json={**NOTICE, "audience": "faculty", "dept": "CP", "semester": 8}).status_code == 400


# --- publish: every recipient gets their own email, sent in the background ------------------------


def test_publish_emails_every_recipient_once_with_the_previewed_text(adm, undo, mail):
    preview = client.post("/api/admin/announcements/preview", headers=adm, json=NOTICE).json()
    r = client.post("/api/admin/announcements", headers=adm, json={**NOTICE, "email_subject": preview["email"]["subject"], "email_body": preview["email"]["body"]})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["recipients"] == 44 and out["emails_queued"] == 44 and out["emails_held"] == 0

    rows = _outbox(out["announcement_id"])
    assert len(rows) == 44 and {x.status for x in rows} == {"sent"}  # the background task ran
    assert len({x.idempotency_key for x in rows}) == 44
    assert len(mail.sent) == 44 and {m["to"] for m in mail.sent} == {x.to_addr for x in rows}
    assert {m["body"] for m in mail.sent} == {preview["email"]["body"]}  # byte-for-byte what the admin approved
    assert {m["subject"] for m in mail.sent} == {preview["email"]["subject"]}


def test_demo_mode_sends_exactly_four_and_records_the_rest_as_held(adm, undo, mail, demo_mode):
    out = client.post("/api/admin/announcements", headers=adm, json={**NOTICE, "audience": "all", "dept": "CP"}).json()
    assert out["recipients"] == 48 and out["emails_queued"] == 4 and out["emails_held"] == 44

    assert len(mail.sent) == 4  # held messages were never handed to the transport
    assert {m["to"] for m in mail.sent} == {INBOX}  # all four went to the one real inbox...
    assert all(m["headers"].get("X-UniAssist-Intended-To", "").endswith("@sot.pdpu.ac.in") for m in mail.sent)  # ...tagged with who they were for
    roles = {m["headers"]["X-UniAssist-Intended-To"].split("@")[0][:2].isdigit() for m in mail.sent}
    assert roles == {True, False}  # a student-style roll number address and a faculty one: both kinds show up

    rows = _outbox(out["announcement_id"])
    by_status = {s: sum(x.status == s for x in rows) for s in ("sent", "held")}
    assert by_status == {"sent": 4, "held": 44}
    assert all("demo cap" in x.error for x in rows if x.status == "held")

    delivery = client.get("/api/admin/announcements", headers=adm).json()[0]["delivery"]
    assert (delivery["sent"], delivery["held"], delivery["total"]) == (4, 44, 48)


def test_publish_creates_the_in_app_notice_students_see(adm, undo, mail):
    sem3_only = {"title": "Sem 3 timetable", "body": "Revised timetable is on the notice board.", "audience": "student", "semester": 3}
    assert client.post("/api/admin/announcements", headers=adm, json=sem3_only).status_code == 201
    titles = lambda ref: [a["title"] for a in client.get("/api/student/dashboard", headers=_login(ref)).json()["announcements"]]  # noqa: E731
    assert "Sem 3 timetable" in titles("student:17")  # semester 3
    assert "Sem 3 timetable" not in titles("student:57")  # semester 1: the notice is not for them


def test_a_double_submit_creates_one_notice_and_one_set_of_emails(adm, undo, mail):
    first = client.post("/api/admin/announcements", headers=adm, json=NOTICE)
    again = client.post("/api/admin/announcements", headers=adm, json=NOTICE)
    assert first.status_code == 201 and again.status_code == 409
    assert "already published" in again.json()["detail"]
    assert len(mail.sent) == 44


def test_queueing_the_same_announcement_twice_adds_nothing(db, undo):
    admin = make_ctx("admin")
    first = REGISTRY.invoke("publish_notice", admin, db, NOTICE, confirmed=True)
    db.commit()
    recipients = resolve_recipients(db, "student", term=TERM, dept="CP")
    queued, held = queue_announcement_emails(db, first["announcement_id"], recipients, "s", "b")
    assert (queued, held) == (0, 0)  # the idempotency keys already exist


def test_email_off_publishes_the_notice_without_any_mail(adm, undo, mail, monkeypatch):
    monkeypatch.setattr(settings, "email_mode", "off")
    preview = client.post("/api/admin/announcements/preview", headers=adm, json=NOTICE).json()
    assert preview["emailing"] is False and preview["preview"]["emails_to_send"] == 0
    out = client.post("/api/admin/announcements", headers=adm, json=NOTICE).json()
    assert out["emails_queued"] == 0 and "Emailing" not in out["message"]
    assert _outbox(out["announcement_id"]) == [] and mail.sent == []


def test_an_admin_can_edit_the_email_before_publishing(adm, undo, mail):
    edited = {**NOTICE, "email_subject": "Room change: DBMS lab", "email_body": "Dear students, the DBMS lab is now in B-12."}
    assert client.post("/api/admin/announcements", headers=adm, json=edited).status_code == 201
    assert {m["subject"] for m in mail.sent} == {"Room change: DBMS lab"}
    assert {m["body"] for m in mail.sent} == {"Dear students, the DBMS lab is now in B-12."}


def test_delivery_detail_lists_each_recipients_status(adm, undo, mail, demo_mode):
    out = client.post("/api/admin/announcements", headers=adm, json=NOTICE).json()
    detail = client.get(f"/api/admin/announcements/{out['announcement_id']}/deliveries", headers=adm).json()
    assert detail["delivery"]["total"] == 44 and len(detail["emails"]) == 44
    assert {e["status"] for e in detail["emails"]} == {"sent", "held"}
    assert client.get("/api/admin/announcements/999999/deliveries", headers=adm).status_code == 404


# --- the chat path shares the same service ------------------------------------------------------------


def test_confirming_a_notice_in_chat_emails_the_audience_too(undo, mail, demo_mode):
    ctx = make_ctx("admin")
    with SessionLocal() as s:
        pending = REGISTRY.invoke("publish_notice", ctx, s, {**NOTICE, "audience": "all"})
    assert pending["needs_confirmation"]
    assert pending["preview"]["emails_to_send"] == 4 and "email_preview" in pending["preview"]

    r = client.post("/api/chat/confirm", headers=_login("admin:1"), json={"token": pending["token"]})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["emails_queued"] == 4 and r.json()["result"]["emails_held"] > 0
    assert len(mail.sent) == 4


def test_the_chat_preview_freezes_the_email_text_into_the_signed_args(undo):
    ctx = make_ctx("admin")
    with SessionLocal() as s:
        pending = REGISTRY.invoke("publish_notice", ctx, s, NOTICE)
    from app.ai.tools import confirm

    _tool, args = confirm.verify(pending["token"], user_id=ctx.user_id)
    assert args["email_body"] == pending["preview"]["email_preview"]["body"]
    assert args["email_subject"] == pending["preview"]["email_preview"]["subject"]


# --- fees -------------------------------------------------------------------------------------------


def test_fee_list_filters_counts_and_pages(adm):
    page = client.get("/api/admin/fees", headers=adm, params={"dept": "cp", "page_size": 10}).json()
    assert page["term"] == TERM and len(page["fees"]) == 10 and page["total"] == 44
    assert sum(page["counts"].values()) == 44 and set(page["counts"]) == {"paid", "partial", "unpaid", "overdue"}
    assert all(f["dept_code"] == "CP" for f in page["fees"])

    unpaid = client.get("/api/admin/fees", headers=adm, params={"status": "unpaid", "page_size": 100}).json()
    assert unpaid["total"] == unpaid["counts"]["unpaid"] == 8 and all(f["status"] == "unpaid" for f in unpaid["fees"])
    assert unpaid["counts"]["paid"] == 72  # the chips count the set without the status filter

    found = client.get("/api/admin/fees", headers=adm, params={"q": "25BCP017"}).json()
    assert [f["roll_no"] for f in found["fees"]] == ["25BCP017"]

    second = client.get("/api/admin/fees", headers=adm, params={"dept": "CP", "page": 2, "page_size": 40}).json()
    assert len(second["fees"]) == 4
    assert client.get("/api/admin/fees", headers=adm, params={"status": "bogus"}).status_code == 422


def test_fee_list_agrees_with_the_assistants_collection_summary(adm):
    with SessionLocal() as s:
        summary = {r["dept"]: r for r in REGISTRY.get("get_fee_collection_summary").fn(ctx=make_ctx("admin"), db=s)}
    for dept in ("CP", "IT"):
        rows = client.get("/api/admin/fees", headers=adm, params={"dept": dept, "page_size": 100}).json()["fees"]
        assert round(sum(f["amount_paid"] for f in rows), 2) == summary[dept]["collected"]


def test_a_part_payment_then_the_balance_settles_the_fee(adm, undo):
    url = f"/api/admin/fees/{PARTIAL_FEE}/payment"
    first = client.post(url, headers=adm, json={"amount": 1400, "paid_on": date.today().isoformat()})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "partial" and first.json()["fee"]["outstanding"] == 80000.0
    assert first.json()["fee"]["amount_paid"] == 72500.0

    last = client.post(url, headers=adm, json={"amount": 80000})
    assert last.json()["status"] == "paid" and last.json()["fee"]["outstanding"] == 0

    # the student sees it on their own dashboard
    dash = client.get("/api/student/dashboard", headers=_login("student:2")).json()["fees"]
    assert dash["all_paid"] is True and dash["outstanding"] == 0


def test_payments_are_validated(adm, undo):
    url = f"/api/admin/fees/{PARTIAL_FEE}/payment"
    over = client.post(url, headers=adm, json={"amount": 999999})
    assert over.status_code == 400 and "more than" in over.json()["detail"]
    assert client.post(url, headers=adm, json={"amount": 0}).status_code == 422
    assert client.post(url, headers=adm, json={"amount": -5}).status_code == 422
    future = (date.today() + timedelta(days=2)).isoformat()
    assert client.post(url, headers=adm, json={"amount": 100, "paid_on": future}).status_code == 400
    already = client.post(f"/api/admin/fees/{PAID_FEE}/payment", headers=adm, json={"amount": 10})
    assert already.status_code == 409 and "already paid" in already.json()["detail"]
    assert client.post("/api/admin/fees/999999/payment", headers=adm, json={"amount": 10}).status_code == 404
    with SessionLocal() as s:
        assert float(s.get(Fee, PARTIAL_FEE).amount_paid) == 71100.0  # nothing above wrote


def test_the_fee_tool_previews_before_it_writes_and_is_audited(db, undo):
    admin = make_ctx("admin")
    args = {"student_roll_no": "25bcp002", "amount": 5000}
    preview = REGISTRY.invoke("record_fee_payment", admin, db, args)
    assert preview["needs_confirmation"] and preview["preview"]["outstanding_after"] == 76400.0
    assert preview["preview"]["status_after"] == "partial" and float(db.get(Fee, PARTIAL_FEE).amount_paid) == 71100.0
    done = REGISTRY.invoke("record_fee_payment", admin, db, args, confirmed=True)
    db.commit()
    assert done["done"] and float(db.get(Fee, PARTIAL_FEE).amount_paid) == 76100.0
    for bad, fragment in (
        ({"student_roll_no": "25BCP999", "amount": 1}, "no student"),
        ({"student_roll_no": "25BCP002", "amount": 1, "term": "1999-00-ODD"}, "no fee record"),
        ({"student_roll_no": "25BCP002", "amount": "lots"}, "must be a number"),
    ):
        assert fragment in REGISTRY.invoke("record_fee_payment", admin, db, bad)["error"]


def test_the_model_can_name_the_student_it_is_charging():
    from app.ai.tools.schema import function_schema

    props = function_schema(REGISTRY.get("record_fee_payment"))["function"]["parameters"]["properties"]
    assert {"student_roll_no", "amount"} <= props.keys()  # `roll_no` would be hidden as an identity argument


# --- who may call, and the dashboard ------------------------------------------------------------------


def test_admin_routes_are_admin_only():
    paths = [
        ("get", "/api/admin/dashboard"),
        ("get", "/api/admin/fees"),
        ("get", "/api/admin/announcements"),
        ("post", "/api/admin/announcements"),
        ("post", "/api/admin/announcements/preview"),
        ("post", f"/api/admin/fees/{PARTIAL_FEE}/payment"),
    ]
    for ref in ("student:17", "faculty:2"):
        h = _login(ref)
        for verb, path in paths:
            assert getattr(client, verb)(path, headers=h).status_code == 403, (ref, path)
    for verb, path in paths:
        assert getattr(client, verb)(path).status_code in (401, 403), path


def test_admin_dashboard_totals_agree_with_the_records(adm):
    d = client.get("/api/admin/dashboard", headers=adm).json()
    k = d["kpis"]
    with SessionLocal() as s:
        assert k["students"] == s.scalar(select(func.count(Student.id)).where(Student.is_active.is_(True)))
        billed = float(s.scalar(select(func.sum(Fee.amount_due)).where(Fee.term == TERM)))
        collected = float(s.scalar(select(func.sum(Fee.amount_paid)).where(Fee.term == TERM)))
    assert k["fees_billed"] == billed and k["fees_collected"] == collected
    assert k["fees_outstanding"] == round(billed - collected, 2)
    assert len(d["departments"]) == 7 == k["departments"] and all("fee_collection_percent" in r for r in d["departments"])
    assert 0 < k["avg_attendance_percent"] <= 100 and isinstance(d["recent_announcements"], list)
