"""Announcements that email their audience — the agentic half of `publish_notice`.

An announcement is one in-app row (everyone in its audience sees it in their
feed) plus one outbox email per recipient. Nothing goes out when it is
submitted: each department it reaches has an `announcement_approvals` row, and
only that department's HOD releases it to that department (`decide_announcement`).
This module owns the parts that are not tool plumbing: who the recipients are,
which departments must approve, which recipients are really emailed while the
demo cap is on, and queueing the messages.

Demo cap: while EMAIL_REDIRECT_TO is set, every message lands in one real inbox,
so an announcement to 112 students would bury it. Only `EMAIL_DEMO_CAP`
recipients are really sent — spread across students and faculty so both kinds
of message show up — and the rest are recorded as `held`, so the delivery
breakdown still shows the full fan-out. The cap is per announcement, not per
release: when seven HODs each release a university notice, the seven slices
share the one allowance. Without a redirect (Mailpit, an allowlisted domain,
tests) there is no cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Announcement,
    AnnouncementApproval,
    CourseOffering,
    Department,
    EmailOutbox,
    Enrollment,
    Faculty,
    Student,
)
from app.notify.mailer import queue_email

AUDIENCES = ("all", "student", "faculty")
AUDIENCE_ROLES = {"all": "student,faculty,admin", "student": "student", "faculty": "faculty"}
ROLES_AUDIENCE = {v: k for k, v in AUDIENCE_ROLES.items()}
DUPLICATE_WINDOW = timedelta(seconds=60)
_WHO = {"all": "Students and Faculty", "student": "Students", "faculty": "Faculty"}


@dataclass(frozen=True)
class Recipient:
    role: str  # student | faculty
    name: str
    email: str
    dept: str | None = None  # whose HOD releases the notice to this person


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
        out += [
            Recipient("student", s.full_name, s.university_email, s.dept_code)
            for s in db.scalars(q.order_by(Student.roll_no))
        ]
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
        out += [
            Recipient("faculty", f.full_name, f.university_email, f.dept_code)
            for f in db.scalars(q.order_by(Faculty.employee_id))
        ]
    return [r for r in out if r.email]


def approval_departments(recipients: list[Recipient]) -> list[str]:
    """The departments whose HOD must approve: every department the notice reaches."""
    return sorted({r.dept for r in recipients if r.dept})


def hods(db: Session, dept_codes: list[str]) -> dict[str, Faculty | None]:
    """Each department's head, or None where the post is vacant."""
    rows = db.execute(
        select(Department.code, Faculty)
        .outerjoin(Faculty, Faculty.id == Department.hod_faculty_id)
        .where(Department.code.in_(dept_codes))
    )
    found = {code: f for code, f in rows}
    return {code: found.get(code) for code in dept_codes}


def course_reach(db: Session, course_code: str, term: str) -> int:
    """Students enrolled in any section of the course this term: who a course notice reaches."""
    return db.scalar(
        select(func.count(func.distinct(Enrollment.student_id)))
        .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
        .where(CourseOffering.subject_code == course_code, CourseOffering.term == term, Enrollment.status == "enrolled")
    ) or 0


def approvals_for(db: Session, announcement_ids: list[int]) -> dict[int, list[dict]]:
    """Per announcement, each department's approval: status, who decided, when, and why."""
    out: dict[int, list[dict]] = {i: [] for i in announcement_ids}
    if not announcement_ids:
        return out
    hod = Faculty.__table__.alias("hod")
    decider = Faculty.__table__.alias("decider")
    rows = db.execute(
        select(AnnouncementApproval, hod.c.full_name, decider.c.full_name)
        .outerjoin(Department, Department.code == AnnouncementApproval.dept_code)
        .outerjoin(hod, hod.c.id == Department.hod_faculty_id)
        .outerjoin(decider, decider.c.id == AnnouncementApproval.decided_by)
        .where(AnnouncementApproval.announcement_id.in_(announcement_ids))
        .order_by(AnnouncementApproval.dept_code)
    )
    for a, hod_name, decided_by in rows:
        out[a.announcement_id].append(
            {
                "dept": a.dept_code,
                "status": a.status,
                "hod": hod_name,
                "decided_by": decided_by,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                "note": a.note,
            }
        )
    return out


def approval_state(approvals: list[dict]) -> str:
    """One word for a notice: pending (no HOD has decided), approved, rejected, or partial."""
    seen = {a["status"] for a in approvals}
    if not seen or seen == {"pending"}:
        return "pending"
    if seen == {"approved"}:
        return "approved"
    if seen == {"rejected"}:
        return "rejected"
    return "partial"


def demo_cap_active() -> bool:
    return bool(settings.email_redirect_to) and settings.email_demo_cap > 0


def demo_split(recipients: list[Recipient], budget: int | None = None) -> tuple[list[Recipient], list[Recipient]]:
    """(really emailed, held back) under the demo cap; everyone is emailed when it is off.

    `budget` is what is left of the cap for this announcement (earlier releases of
    the same notice to other departments have used the rest); the full cap if omitted.
    """
    if not demo_cap_active():
        return list(recipients), []
    cap = settings.email_demo_cap if budget is None else max(0, min(budget, settings.email_demo_cap))
    if len(recipients) <= cap:
        return list(recipients), []
    pools = [[r for r in recipients if r.role == role] for role in ("student", "faculty")]
    chosen: list[Recipient] = []
    while len(chosen) < cap and any(pools):
        for pool in pools:  # alternate roles so a mixed audience shows both kinds of message
            if pool and len(chosen) < cap:
                chosen.append(pool.pop(0))
    picked = set(chosen)
    return chosen, [r for r in recipients if r not in picked]


def queue_announcement_emails(
    db: Session, announcement_id: int, recipients: list[Recipient], subject: str, body: str
) -> tuple[int, int]:
    """Write one outbox row per recipient; returns (queued to send, held by the demo cap).

    Idempotent per (announcement, address): a replayed release queues nothing twice.
    Nothing is sent here: the caller flushes after its transaction commits.
    """
    sent, held = demo_split(recipients, demo_budget(db, announcement_id))
    reason = (
        f"demo cap: only {settings.email_demo_cap} recipients of an announcement are really emailed while EMAIL_REDIRECT_TO is set"
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


def demo_budget(db: Session, announcement_id: int) -> int | None:
    """How much of the demo cap this announcement has left, or None when there is no cap."""
    if not demo_cap_active():
        return None
    used = db.scalar(
        select(func.count(EmailOutbox.id)).where(
            EmailOutbox.related_type == "announcement",
            EmailOutbox.related_id == announcement_id,
            EmailOutbox.status.in_(("queued", "sent", "failed")),  # really sent, or tried to be
        )
    )
    return settings.email_demo_cap - (used or 0)


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
