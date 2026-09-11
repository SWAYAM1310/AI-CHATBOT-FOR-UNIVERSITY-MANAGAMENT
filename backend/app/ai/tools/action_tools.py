"""Action tools — the writes, all two-phase (plan.md §6 "Action tools", §7).

Every tool here has one code path: validate → build the preview → and then
EITHER return `confirm.pending(...)` (the default: nothing is written, the turn
stops on a confirm card) OR, when the registry passes `confirmed=True` from a
verified token, perform the write and return `{"done": True, "message": ...}`.

Running validation on both passes is deliberate. The token freezes the
arguments, not the world: a leave that was clear at preview time may overlap
one approved in the meantime, and the second pass catches that.

Validation failures come back as `{"error": ...}` rather than raising, so the
synthesis call can tell the user *what* was wrong ("that date is in the past")
instead of the orchestrator logging "(tool failed)".

Scope gates reuse the read tools' machinery: a faculty member writes only into
offerings where `course_offerings.faculty_id` is their own, an HOD decides
leave only for their own department's students, and a student's writes are
pinned to `ctx.student_id` — never to a roll number the model supplied.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.tools import confirm
from app.ai.tools.registry import Scope, tool
from app.auth.context import AuthContext, Role
from app.auth.security import hash_password
from app.models import (
    Announcement,
    Assessment,
    AttendanceRecord,
    AttendanceSession,
    CourseOffering,
    Department,
    DocumentRequest,
    Enrollment,
    Faculty,
    LeaveRequest,
    Mark,
    Student,
    User,
)

MAX_LEAVE_DAYS = 10
MAX_TITLE_CHARS = 120
MAX_BODY_CHARS = 2000
DOC_TYPES = (  # what document_requests.doc_type holds today
    "Bonafide Certificate",
    "Bus Pass",
    "Course Completion Letter",
    "Fee Payment Receipt",
    "Internship NOC",
    "Migration Certificate",
    "Official Transcript",
)
LEAVE_DECISIONS = {"approve": "approved", "reject": "rejected"}
NOTICE_AUDIENCES = {"all": "student,faculty,admin", "student": "student", "faculty": "faculty"}
USER_ACTIONS = ("activate", "deactivate", "reset_password")
TEMP_PASSWORD_BYTES = 9


def _today() -> date:  # a function so tests can pin the calendar
    return date.today()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _error(msg: str) -> dict[str, Any]:
    return {"error": msg}


def _parse_date(raw: Any, label: str) -> date | dict[str, Any]:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return _error(f"{label} must be a date in YYYY-MM-DD form")


def _own_offering(
    db: Session, ctx: AuthContext, course_code: str, division: str | None, lab_group: str | None
) -> CourseOffering | dict[str, Any]:
    """Exactly one offering of `course_code` the caller teaches this term, or an error.

    Lab and theory have distinct codes, so ambiguity only arises when the same
    faculty takes the same course for two divisions / lab groups — then the
    model has to say which.
    """
    q = select(CourseOffering).where(
        CourseOffering.subject_code == course_code.upper(), CourseOffering.term == ctx.term
    )
    if ctx.role is Role.FACULTY:
        q = q.where(CourseOffering.faculty_id == ctx.faculty_id)
    if division:
        q = q.where(CourseOffering.division == str(division))
    if lab_group:
        q = q.where(CourseOffering.lab_group == lab_group.upper())
    rows = list(db.scalars(q))
    if not rows:
        return _error(f"you do not teach {course_code.upper()} this term")
    if len(rows) > 1:
        choices = ", ".join(f"division {r.division or '-'} / lab group {r.lab_group or '-'}" for r in rows)
        return _error(f"{course_code.upper()} has several sections for you ({choices}); say which")
    return rows[0]


def _roster(db: Session, offering_id: int) -> dict[str, Student]:
    rows = db.scalars(
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.offering_id == offering_id, Enrollment.status == "enrolled")
    )
    return {s.roll_no: s for s in rows}


def _hod_name(db: Session, dept_id: int | None) -> str | None:
    if dept_id is None:
        return None
    return db.scalar(
        select(Faculty.full_name)
        .join(Department, Department.hod_faculty_id == Faculty.id)
        .where(Department.id == dept_id)
    )


# --- student ------------------------------------------------------------------

@tool(
    name="apply_for_leave",
    description="Submit a leave application for the calling student (from_date, to_date as YYYY-MM-DD, reason). Asks for confirmation before submitting.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
    action=True,
)
def apply_for_leave(
    *, ctx: AuthContext, db: Session, from_date: str, to_date: str, reason: str, confirmed: bool = False, **_: Any
) -> dict[str, Any]:
    start = _parse_date(from_date, "from_date")
    if isinstance(start, dict):
        return start
    end = _parse_date(to_date, "to_date")
    if isinstance(end, dict):
        return end
    if end < start:
        return _error("to_date is before from_date")
    if start < _today():
        return _error("leave cannot start in the past")
    days = (end - start).days + 1
    if days > MAX_LEAVE_DAYS:
        return _error(f"a single leave request may cover at most {MAX_LEAVE_DAYS} days")
    reason = (reason or "").strip()
    if not reason:
        return _error("a reason is required")

    clash = db.scalar(
        select(LeaveRequest.id)
        .where(
            LeaveRequest.student_id == ctx.student_id,
            LeaveRequest.status.in_(("pending", "approved")),
            LeaveRequest.from_date <= end,
            LeaveRequest.to_date >= start,
        )
        .limit(1)
    )
    if clash:
        return _error(f"overlaps your existing leave request #{clash}")

    student = db.get(Student, ctx.student_id)
    approver = _hod_name(db, ctx.dept_id)
    args = {"from_date": start.isoformat(), "to_date": end.isoformat(), "reason": reason}
    preview = {
        "summary": f"Apply for {days}-day leave, {start.isoformat()} to {end.isoformat()}",
        **args,
        "days": days,
        "approver": approver,
    }
    if not confirmed:
        return confirm.pending(ctx, "apply_for_leave", args, preview)

    row = LeaveRequest(
        student_id=student.id,
        roll_no=student.roll_no,
        from_date=start,
        to_date=end,
        reason=reason,
        status="pending",
        applied_on=_today(),
    )
    db.add(row)
    db.flush()
    who = f" from {approver}" if approver else ""
    return {
        "done": True,
        "leave_request_id": row.id,
        "status": "pending",
        "message": f"Leave application #{row.id} submitted ({start.isoformat()} to {end.isoformat()}), pending approval{who}.",
    }


def _match_doc_type(raw: str) -> str | None:
    wanted = (raw or "").strip().lower()
    if not wanted:
        return None
    exact = [t for t in DOC_TYPES if t.lower() == wanted]
    if exact:
        return exact[0]
    partial = [t for t in DOC_TYPES if wanted in t.lower()]
    return partial[0] if len(partial) == 1 else None


@tool(
    name="request_document",
    description="Request an official document for the calling student (bonafide certificate, transcript, bus pass, fee receipt, migration certificate, internship NOC, course completion letter), with an optional purpose. Asks for confirmation.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
    action=True,
)
def request_document(
    *, ctx: AuthContext, db: Session, doc_type: str, purpose: str | None = None, confirmed: bool = False, **_: Any
) -> dict[str, Any]:
    kind = _match_doc_type(doc_type)
    if kind is None:
        return _error(f"unknown document type {doc_type!r}; allowed: {', '.join(DOC_TYPES)}")
    purpose = (purpose or "").strip() or None

    open_req = db.scalar(
        select(DocumentRequest.id)
        .where(
            DocumentRequest.student_id == ctx.student_id,
            DocumentRequest.doc_type == kind,
            DocumentRequest.status.in_(("pending", "processing")),
        )
        .limit(1)
    )
    if open_req:
        return _error(f"you already have an open request #{open_req} for a {kind}")

    args = {"doc_type": kind, "purpose": purpose}
    preview = {"summary": f"Request a {kind}", **args}
    if not confirmed:
        return confirm.pending(ctx, "request_document", args, preview)

    student = db.get(Student, ctx.student_id)
    row = DocumentRequest(
        student_id=student.id,
        roll_no=student.roll_no,
        doc_type=kind,
        purpose=purpose,
        status="processing",
        requested_on=_today(),
    )
    db.add(row)
    db.flush()
    return {
        "done": True,
        "document_request_id": row.id,
        "status": "processing",
        "message": f"Request #{row.id} for a {kind} submitted; you will be told when it is ready to collect.",
    }


# --- faculty ------------------------------------------------------------------

def _roll_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [str(r).strip().upper() for r in raw if str(r).strip()]


@tool(
    name="mark_attendance",
    description="Record attendance for one session of a course you teach: everyone enrolled is marked present except the roll numbers listed as absent. Asks for confirmation.",
    allowed_roles={Role.FACULTY},
    scope=Scope.OWN_COURSES,
    action=True,
)
def mark_attendance(
    *,
    ctx: AuthContext,
    db: Session,
    course_code: str,
    date: str,
    absent_roll_nos: list[str] | None = None,
    slot_no: int | None = None,
    division: str | None = None,
    lab_group: str | None = None,
    confirmed: bool = False,
    **_: Any,
) -> dict[str, Any]:
    offering = _own_offering(db, ctx, course_code, division, lab_group)
    if isinstance(offering, dict):
        return offering
    when = _parse_date(date, "date")
    if isinstance(when, dict):
        return when
    if when > _today():
        return _error("attendance cannot be marked for a future date")

    roster = _roster(db, offering.id)
    if not roster:
        return _error(f"no students are enrolled in {offering.subject_code}")
    absent = sorted(set(_roll_list(absent_roll_nos)))
    unknown = [r for r in absent if r not in roster]
    if unknown:
        return _error(f"not enrolled in {offering.subject_code}: {', '.join(unknown)}")

    dup = select(AttendanceSession.id).where(
        AttendanceSession.offering_id == offering.id, AttendanceSession.session_date == when
    )
    if slot_no is not None:
        dup = dup.where(AttendanceSession.slot_no == slot_no)
    if db.scalar(dup.limit(1)):
        return _error(f"attendance for {offering.subject_code} on {when.isoformat()} is already recorded")

    args = {
        "course_code": offering.subject_code,
        "date": when.isoformat(),
        "absent_roll_nos": absent,
        "slot_no": slot_no,
        "division": offering.division,
        "lab_group": offering.lab_group,
    }
    preview = {
        "summary": f"Mark {offering.subject_code} on {when.isoformat()}: {len(roster) - len(absent)} present, {len(absent)} absent",
        **args,
        "present": len(roster) - len(absent),
        "absent": [f"{r} {roster[r].full_name}" for r in absent],
    }
    if not confirmed:
        return confirm.pending(ctx, "mark_attendance", args, preview)

    session = AttendanceSession(
        offering_id=offering.id,
        subject_code=offering.subject_code,
        session_date=when,
        slot_no=slot_no,
        marked_by=ctx.faculty_id,
        marked_at=_now(),
    )
    db.add(session)
    db.flush()
    absent_set = set(absent)
    db.add_all(
        AttendanceRecord(session_id=session.id, student_id=s.id, status="absent" if roll in absent_set else "present")
        for roll, s in roster.items()
    )
    db.flush()
    return {
        "done": True,
        "session_id": session.id,
        "present": len(roster) - len(absent),
        "absent": len(absent),
        "message": f"Attendance for {offering.subject_code} on {when.isoformat()} recorded: {len(roster) - len(absent)} present, {len(absent)} absent.",
    }


def _mark_entries(raw: Any) -> dict[str, Any] | list[tuple[str, Decimal]]:
    """Accept {"25BCP017": 18} or [{"roll_no": "25BCP017", "score": 18}]; normalise."""
    pairs: list[tuple[str, Any]] = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or "roll_no" not in item or "score" not in item:
                return _error("each marks entry needs roll_no and score")
            pairs.append((item["roll_no"], item["score"]))
    else:
        return _error("marks must map roll numbers to scores")
    out: list[tuple[str, Decimal]] = []
    for roll, score in pairs:
        try:
            out.append((str(roll).strip().upper(), Decimal(str(score))))
        except (InvalidOperation, ValueError):
            return _error(f"score for {roll} is not a number")
    if not out:
        return _error("no marks given")
    return out


@tool(
    name="enter_marks",
    description="Enter or update scores for one assessment of a course you teach; marks maps roll numbers to scores. Asks for confirmation.",
    allowed_roles={Role.FACULTY},
    scope=Scope.OWN_COURSES,
    action=True,
)
def enter_marks(
    *,
    ctx: AuthContext,
    db: Session,
    course_code: str,
    assessment: str,
    marks: dict[str, float],
    division: str | None = None,
    lab_group: str | None = None,
    confirmed: bool = False,
    **_: Any,
) -> dict[str, Any]:
    offering = _own_offering(db, ctx, course_code, division, lab_group)
    if isinstance(offering, dict):
        return offering
    wanted = (assessment or "").strip().lower()
    own = select(Assessment).where(Assessment.offering_id == offering.id)
    target = None
    if wanted:  # by type ("Assignment-1") first, then by title
        target = (
            db.scalars(own.where(func.lower(Assessment.type) == wanted)).first()
            or db.scalars(own.where(func.lower(Assessment.title) == wanted)).first()
        )
    if target is None:
        names = sorted({a.type for a in db.scalars(own)})
        return _error(f"no assessment {assessment!r} in {offering.subject_code}; have: {', '.join(names)}")

    entries = _mark_entries(marks)
    if isinstance(entries, dict):
        return entries
    roster = _roster(db, offering.id)
    max_marks = Decimal(target.max_marks) if target.max_marks is not None else None
    for roll, score in entries:
        if roll not in roster:
            return _error(f"{roll} is not enrolled in {offering.subject_code}")
        if score < 0 or (max_marks is not None and score > max_marks):
            return _error(f"score {score} for {roll} is outside 0..{max_marks}")

    clean = {roll: float(score) for roll, score in entries}
    args = {
        "course_code": offering.subject_code,
        "assessment": target.type,
        "marks": clean,
        "division": offering.division,
        "lab_group": offering.lab_group,
    }
    preview = {
        "summary": f"Enter {len(clean)} score(s) for {target.title or target.type} in {offering.subject_code}",
        **args,
        "max_marks": float(max_marks) if max_marks is not None else None,
    }
    if not confirmed:
        return confirm.pending(ctx, "enter_marks", args, preview)

    existing = {
        m.student_id: m
        for m in db.scalars(select(Mark).where(Mark.assessment_id == target.id))
    }
    inserted = updated = 0
    for roll, score in entries:
        sid = roster[roll].id
        row = existing.get(sid)
        if row is None:
            db.add(Mark(assessment_id=target.id, student_id=sid, score=score, is_absent=False, graded_on=_today()))
            inserted += 1
        else:
            row.score, row.is_absent, row.graded_on = score, False, _today()
            updated += 1
    db.flush()
    return {
        "done": True,
        "assessment_id": target.id,
        "inserted": inserted,
        "updated": updated,
        "message": f"Marks for {target.title or target.type} in {offering.subject_code} saved: {inserted} new, {updated} updated.",
    }


def _clean_text(title: str, body: str) -> tuple[str, str] | dict[str, Any]:
    title, body = (title or "").strip(), (body or "").strip()
    if not title or not body:
        return _error("both a title and a body are required")
    if len(title) > MAX_TITLE_CHARS:
        return _error(f"title is longer than {MAX_TITLE_CHARS} characters")
    if len(body) > MAX_BODY_CHARS:
        return _error(f"body is longer than {MAX_BODY_CHARS} characters")
    return title, body


@tool(
    name="post_announcement",
    description="Post an announcement to the students of a course you teach (title, body). Asks for confirmation.",
    allowed_roles={Role.FACULTY},
    scope=Scope.OWN_COURSES,
    action=True,
)
def post_announcement(
    *, ctx: AuthContext, db: Session, course_code: str, title: str, body: str, confirmed: bool = False, **_: Any
) -> dict[str, Any]:
    code = course_code.upper()
    teaches = db.scalar(
        select(CourseOffering.id)
        .where(
            CourseOffering.subject_code == code,
            CourseOffering.term == ctx.term,
            CourseOffering.faculty_id == ctx.faculty_id,
        )
        .limit(1)
    )
    if not teaches:
        return _error(f"you do not teach {code} this term")
    text = _clean_text(title, body)
    if isinstance(text, dict):
        return text
    title, body = text

    args = {"course_code": code, "title": title, "body": body}
    preview = {"summary": f"Post \"{title}\" to {code} students", **args, "audience": "student"}
    if not confirmed:
        return confirm.pending(ctx, "post_announcement", args, preview)

    row = Announcement(
        author_user_id=ctx.user_id,
        scope="course",
        scope_ref=code,
        title=title,
        body=body,
        audience_roles="student",
        posted_at=_now(),
    )
    db.add(row)
    db.flush()
    return {"done": True, "announcement_id": row.id, "message": f"Announcement \"{title}\" posted to {code}."}


def _department_pending(db: Session, ctx: AuthContext):
    return (
        select(LeaveRequest, Student.full_name)
        .join(Student, Student.id == LeaveRequest.student_id)
        .where(Student.dept_id == ctx.dept_id, LeaveRequest.status == "pending")
        .order_by(LeaveRequest.from_date, LeaveRequest.id)
    )


@tool(
    name="list_pending_leave_requests",
    description="Leave requests awaiting a decision from the calling faculty member as head of department (empty unless you are an HOD).",
    allowed_roles={Role.FACULTY},
    scope=Scope.OWN_DEPARTMENT,
)
def list_pending_leave_requests(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    if not ctx.is_hod:
        return []
    return [
        {
            "leave_request_id": r.id,
            "roll_no": r.roll_no,
            "full_name": name,
            "from_date": r.from_date.isoformat(),
            "to_date": r.to_date.isoformat(),
            "reason": r.reason,
            "applied_on": r.applied_on.isoformat() if r.applied_on else None,
        }
        for r, name in db.execute(_department_pending(db, ctx))
    ]


@tool(
    name="decide_leave_request",
    description="Approve or reject a pending student leave request by id, as head of the student's department. Asks for confirmation.",
    allowed_roles={Role.FACULTY},
    scope=Scope.OWN_DEPARTMENT,
    action=True,
)
def decide_leave_request(
    *, ctx: AuthContext, db: Session, leave_request_id: int, decision: str, confirmed: bool = False, **_: Any
) -> dict[str, Any]:
    verb = {"approve": "approve", "approved": "approve", "reject": "reject", "rejected": "reject"}.get(
        (decision or "").strip().lower()
    )
    if verb is None:
        return _error("decision must be 'approve' or 'reject'")
    try:
        req_id = int(leave_request_id)
    except (TypeError, ValueError):
        return _error("leave_request_id must be a number")

    if not ctx.is_hod:
        return _error("only a head of department can decide leave requests")
    row = db.execute(
        select(LeaveRequest, Student)
        .join(Student, Student.id == LeaveRequest.student_id)
        .where(LeaveRequest.id == req_id)
    ).first()
    if row is None or row.Student.dept_id != ctx.dept_id:
        return _error(f"no leave request #{req_id} in your department")
    req, student = row.LeaveRequest, row.Student
    if req.status != "pending":
        return _error(f"leave request #{req_id} is already {req.status}")

    args = {"leave_request_id": req_id, "decision": verb}
    preview = {
        "summary": f"{verb.capitalize()} leave request #{req_id} of {student.roll_no} {student.full_name}",
        **args,
        "roll_no": student.roll_no,
        "full_name": student.full_name,
        "from_date": req.from_date.isoformat(),
        "to_date": req.to_date.isoformat(),
        "reason": req.reason,
    }
    if not confirmed:
        return confirm.pending(ctx, "decide_leave_request", args, preview)

    req.status = LEAVE_DECISIONS[verb]
    req.decided_by = ctx.faculty_id
    req.decided_on = _today()
    db.flush()
    return {
        "done": True,
        "leave_request_id": req_id,
        "status": req.status,
        "message": f"Leave request #{req_id} of {student.roll_no} {req.status}.",
    }


# --- admin --------------------------------------------------------------------

@tool(
    name="publish_notice",
    description="Publish a university-wide (or one department's) notice with a title and body; audience is all, student or faculty. Asks for confirmation.",
    allowed_roles={Role.ADMIN},
    scope=Scope.UNIVERSITY,
    action=True,
)
def publish_notice(
    *,
    ctx: AuthContext,
    db: Session,
    title: str,
    body: str,
    audience: str = "all",
    dept: str | None = None,
    confirmed: bool = False,
    **_: Any,
) -> dict[str, Any]:
    text = _clean_text(title, body)
    if isinstance(text, dict):
        return text
    title, body = text
    audience = (audience or "all").strip().lower()
    if audience not in NOTICE_AUDIENCES:
        return _error(f"audience must be one of: {', '.join(NOTICE_AUDIENCES)}")
    scope, scope_ref = "university", None
    if dept:
        code = dept.strip().upper()
        if db.scalar(select(Department.id).where(Department.code == code)) is None:
            return _error(f"no department {code}")
        scope, scope_ref = "department", code

    args = {"title": title, "body": body, "audience": audience, "dept": scope_ref}
    where = f"{scope_ref} department" if scope_ref else "the whole university"
    preview = {"summary": f"Publish \"{title}\" to {audience} in {where}", **args, "scope": scope}
    if not confirmed:
        return confirm.pending(ctx, "publish_notice", args, preview)

    row = Announcement(
        author_user_id=ctx.user_id,
        scope=scope,
        scope_ref=scope_ref,
        title=title,
        body=body,
        audience_roles=NOTICE_AUDIENCES[audience],
        posted_at=_now(),
    )
    db.add(row)
    db.flush()
    return {"done": True, "announcement_id": row.id, "message": f"Notice \"{title}\" published to {audience} in {where}."}


@tool(
    name="manage_user",
    description="Activate, deactivate or reset the password of a user account by email (action: activate | deactivate | reset_password). Asks for confirmation.",
    allowed_roles={Role.ADMIN},
    scope=Scope.UNIVERSITY,
    action=True,
)
def manage_user(
    *, ctx: AuthContext, db: Session, email: str, action: str, confirmed: bool = False, **_: Any
) -> dict[str, Any]:
    action = (action or "").strip().lower()
    if action not in USER_ACTIONS:
        return _error(f"action must be one of: {', '.join(USER_ACTIONS)}")
    email = (email or "").strip().lower()
    user = db.scalars(select(User).where(func.lower(User.email) == email)).first()
    if user is None:
        return _error(f"no account for {email}")
    if user.id == ctx.user_id:
        return _error("you cannot manage your own account here")
    if action == "activate" and user.is_active:
        return _error(f"{email} is already active")
    if action == "deactivate" and not user.is_active:
        return _error(f"{email} is already inactive")

    args = {"email": user.email, "action": action}
    preview = {
        "summary": f"{action.replace('_', ' ').capitalize()} {user.email} ({user.role})",
        **args,
        "role": user.role,
        "currently_active": bool(user.is_active),
    }
    if not confirmed:
        return confirm.pending(ctx, "manage_user", args, preview)

    out: dict[str, Any] = {"done": True, "user_id": user.id, "email": user.email, "action": action}
    if action == "reset_password":
        temp = secrets.token_urlsafe(TEMP_PASSWORD_BYTES)
        user.password_hash = hash_password(temp)
        out["temporary_password"] = temp
        out["message"] = f"Password for {user.email} reset; temporary password: {temp}"
    else:
        user.is_active = action == "activate"
        out["is_active"] = user.is_active
        out["message"] = f"Account {user.email} {'activated' if user.is_active else 'deactivated'}."
    db.flush()
    return out
