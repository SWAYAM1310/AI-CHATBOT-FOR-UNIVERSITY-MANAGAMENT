"""Announcements that email their audience — the agentic half of `publish_notice`.

An announcement is one in-app row (everyone in its audience sees it in their
feed) plus one outbox email per recipient. This module owns the parts that are
not tool plumbing: who the recipients are, which of them are really emailed
while the demo cap is on, and queueing the messages.

Demo cap: while EMAIL_REDIRECT_TO is set, every message lands in one real inbox,
so an announcement to 112 students would bury it. Only `EMAIL_DEMO_CAP`
recipients are really sent — spread across students and faculty so both kinds
of message show up — and the rest are recorded as `held`, so the delivery
breakdown still shows the full fan-out. Without a redirect (Mailpit, an
allowlisted domain, tests) there is no cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Announcement, CourseOffering, Faculty, Student
from app.notify.mailer import queue_email

AUDIENCES = ("all", "student", "faculty")
DUPLICATE_WINDOW = timedelta(seconds=60)
_WHO = {"all": "Students and Faculty", "student": "Students", "faculty": "Faculty"}


@dataclass(frozen=True)
class Recipient:
    role: str  # student | faculty
    name: str
    email: str


def audience_label(audience: str, dept: str | None) -> str:
    """"Students of the CP department" — the greeting and the prompt both use it."""
    who = _WHO[audience]
    return f"{who} of the {dept} department" if dept else who


def resolve_recipients(
    db: Session, audience: str, *, term: str, dept: str | None = None, semester: int | None = None
) -> list[Recipient]:
    """Active students and/or faculty the announcement is for, in a stable order.

    `semester` narrows students to that semester and faculty to those who teach
    a course of that semester this term; `dept` narrows both to the department.
    Admins are not emailed: they author the notice.
    """
    out: list[Recipient] = []
    if audience in ("all", "student"):
        q = select(Student).where(Student.is_active.is_(True))
        if dept:
            q = q.where(Student.dept_code == dept)
        if semester is not None:
            q = q.where(Student.semester == semester)
        out += [Recipient("student", s.full_name, s.university_email) for s in db.scalars(q.order_by(Student.roll_no))]
    if audience in ("all", "faculty"):
        q = select(Faculty).where(Faculty.is_active.is_(True))
        if dept:
            q = q.where(Faculty.dept_code == dept)
        if semester is not None:
            q = q.where(
                Faculty.id.in_(
                    select(CourseOffering.faculty_id).where(
                        CourseOffering.term == term, CourseOffering.semester == semester
                    )
                )
            )
        out += [Recipient("faculty", f.full_name, f.university_email) for f in db.scalars(q.order_by(Faculty.employee_id))]
    return [r for r in out if r.email]


def demo_cap_active() -> bool:
    return bool(settings.email_redirect_to) and settings.email_demo_cap > 0


def demo_split(recipients: list[Recipient]) -> tuple[list[Recipient], list[Recipient]]:
    """(really emailed, held back) under the demo cap; everyone is emailed when it is off."""
    if not demo_cap_active() or len(recipients) <= settings.email_demo_cap:
        return list(recipients), []
    pools = [[r for r in recipients if r.role == role] for role in ("student", "faculty")]
    chosen: list[Recipient] = []
    while len(chosen) < settings.email_demo_cap and any(pools):
        for pool in pools:  # alternate roles so a mixed audience shows both kinds of message
            if pool and len(chosen) < settings.email_demo_cap:
                chosen.append(pool.pop(0))
    picked = set(chosen)
    return chosen, [r for r in recipients if r not in picked]


def queue_announcement_emails(
    db: Session, announcement_id: int, recipients: list[Recipient], subject: str, body: str
) -> tuple[int, int]:
    """Write one outbox row per recipient; returns (queued to send, held by the demo cap).

    Idempotent per (announcement, address): a replayed publish queues nothing twice.
    Nothing is sent here: the caller flushes after its transaction commits.
    """
    sent, held = demo_split(recipients)
    reason = (
        f"demo cap: only {len(sent)} of {len(recipients)} recipients are really emailed while EMAIL_REDIRECT_TO is set"
        if held
        else None
    )
    counts = {"queued": 0, "held": 0}
    for group, hold, key in ((sent, None, "queued"), (held, reason, "held")):
        for r in group:
            row = queue_email(
                db,
                idempotency_key=f"announcement:{announcement_id}:{r.email.lower()}",
                to_addr=r.email,
                subject=subject,
                body=body,
                related_type="announcement",
                related_id=announcement_id,
                hold=hold,
            )
            if row is not None:
                counts[key] += 1
    return counts["queued"], counts["held"]


def find_recent_duplicate(
    db: Session,
    *,
    author_user_id: int,
    title: str,
    body: str,
    scope: str,
    scope_ref: str | None,
    audience_roles: str,
    semester: int | None,
    now: datetime,
) -> Announcement | None:
    """The same notice by the same author a moment ago: a double click or a replayed request."""
    return db.scalars(
        select(Announcement)
        .where(
            Announcement.author_user_id == author_user_id,
            Announcement.title == title,
            Announcement.body == body,
            Announcement.scope == scope,
            Announcement.scope_ref.is_(None) if scope_ref is None else Announcement.scope_ref == scope_ref,
            Announcement.audience_roles == audience_roles,
            Announcement.semester.is_(None) if semester is None else Announcement.semester == semester,
            Announcement.posted_at >= now - DUPLICATE_WINDOW,
        )
        .limit(1)
    ).first()
