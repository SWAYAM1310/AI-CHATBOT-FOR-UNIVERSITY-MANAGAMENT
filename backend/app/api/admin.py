"""Admin portal: university KPIs, fee records and agentic announcements.

Every route is admin-only. Writes call the chat's action tools (`record_fee_payment`,
`publish_notice`) through `app.api.toolcall`, so the website and the assistant
share one set of rules and one audit trail. A notice goes out in two parts: the
in-app announcement and the per-recipient emails are committed together, and the
emails are then sent from a background task, so a large audience never makes the
request wait on SMTP.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.tools.registry import REGISTRY
from app.api.profile import identity_row
from app.api.toolcall import read_tool, run_action
from app.auth.context import AuthContext, Role
from app.auth.deps import get_db, require_roles
from app.models import Announcement, EmailOutbox, Fee, Student
from app.notify.mailer import collecting, flush_in_background

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_roles(Role.ADMIN)

FEE_STATUSES = ("paid", "partial", "unpaid", "overdue")
DELIVERY_STATUSES = ("sent", "queued", "held", "failed", "suppressed")
NOTICE_LIST = 30
DELIVERY_LIST = 300


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    paid_on: Date | None = None


class NoticeIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=2000)
    audience: Literal["all", "student", "faculty"] = "all"
    dept: str | None = Field(default=None, max_length=10)
    semester: int | None = Field(default=None, ge=1, le=8)
    # an admin may edit the drafted email before publishing; omitted, it is drafted again
    email_subject: str | None = Field(default=None, max_length=200)
    email_body: str | None = Field(default=None, max_length=5000)

    def tool_args(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v not in (None, "")}


# --- fees ------------------------------------------------------------------------------------


def _fee_filters(term: str, dept: str | None, q: str | None) -> list[Any]:
    clauses: list[Any] = [Fee.term == term]
    if dept:
        clauses.append(Student.dept_code == dept.strip().upper())
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append(or_(Student.roll_no.ilike(like), Student.full_name.ilike(like)))
    return clauses


def _fee_out(fee: Fee, student: Student) -> dict[str, Any]:
    due, paid = float(fee.amount_due or 0), float(fee.amount_paid or 0)
    return {
        "fee_id": fee.id,
        "roll_no": student.roll_no,
        "full_name": student.full_name,
        "dept_code": student.dept_code,
        "semester": student.semester,
        "term": fee.term,
        "amount_due": due,
        "amount_paid": paid,
        "outstanding": round(due - paid, 2),
        "status": fee.status,
        "due_date": fee.due_date.isoformat() if fee.due_date else None,
        "paid_on": fee.paid_on.isoformat() if fee.paid_on else None,
    }


@router.get("/fees")
def fees(
    term: str | None = None,
    dept: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    ctx: AuthContext = Depends(admin_only),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    term = term or ctx.term
    if status_ and status_ not in FEE_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"status must be one of: {', '.join(FEE_STATUSES)}")
    base = _fee_filters(term, dept, q)

    # the status chips count the filtered set *without* the status filter, so they stay stable as you click
    counts = dict(
        db.execute(
            select(Fee.status, func.count(Fee.id)).join(Student, Student.id == Fee.student_id).where(*base).group_by(Fee.status)
        ).all()
    )
    where = [*base, Fee.status == status_] if status_ else base
    total = db.scalar(select(func.count(Fee.id)).join(Student, Student.id == Fee.student_id).where(*where))
    rows = db.execute(
        select(Fee, Student)
        .join(Student, Student.id == Fee.student_id)
        .where(*where)
        .order_by(Student.roll_no)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "term": term,
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts": {s: counts.get(s, 0) for s in FEE_STATUSES},
        "fees": [_fee_out(f, s) for f, s in rows],
    }


@router.post("/fees/{fee_id}/payment")
def record_payment(
    fee_id: int, body: PaymentIn, ctx: AuthContext = Depends(admin_only), db: Session = Depends(get_db)
) -> dict[str, Any]:
    row = db.execute(select(Fee, Student).join(Student, Student.id == Fee.student_id).where(Fee.id == fee_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such fee record")
    fee, student = row
    args: dict[str, Any] = {"student_roll_no": student.roll_no, "amount": body.amount, "term": fee.term}
    if body.paid_on:
        args["paid_on"] = body.paid_on.isoformat()
    result = run_action(db, ctx, "record_fee_payment", args)
    db.refresh(fee)
    return {**result, "fee": _fee_out(fee, student)}


# --- announcements ---------------------------------------------------------------------------


def _delivery(db: Session, announcement_ids: list[int]) -> dict[int, dict[str, int]]:
    out = {i: {s: 0 for s in DELIVERY_STATUSES} | {"total": 0} for i in announcement_ids}
    if not announcement_ids:
        return out
    rows = db.execute(
        select(EmailOutbox.related_id, EmailOutbox.status, func.count(EmailOutbox.id))
        .where(EmailOutbox.related_type == "announcement", EmailOutbox.related_id.in_(announcement_ids))
        .group_by(EmailOutbox.related_id, EmailOutbox.status)
    )
    for rid, st, n in rows:
        out[rid][st if st in DELIVERY_STATUSES else "failed"] += n
        out[rid]["total"] += n
    return out


def _notice_out(a: Announcement, delivery: dict[str, int]) -> dict[str, Any]:
    return {
        "announcement_id": a.id,
        "title": a.title,
        "body": a.body,
        "scope": a.scope,
        "dept": a.scope_ref if a.scope == "department" else None,
        "audience": a.audience_roles,
        "semester": a.semester,
        "posted_at": a.posted_at.isoformat() if a.posted_at else None,
        "delivery": delivery,
    }


def recent_notices(db: Session, limit: int = NOTICE_LIST) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(Announcement)
            .where(Announcement.scope.in_(("university", "department")))
            .order_by(Announcement.posted_at.desc(), Announcement.id.desc())
            .limit(limit)
        )
    )
    delivery = _delivery(db, [a.id for a in rows])
    return [_notice_out(a, delivery[a.id]) for a in rows]


@router.get("/announcements")
def announcements(ctx: AuthContext = Depends(admin_only), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return recent_notices(db)


@router.get("/announcements/{announcement_id}/deliveries")
def deliveries(announcement_id: int, ctx: AuthContext = Depends(admin_only), db: Session = Depends(get_db)) -> dict[str, Any]:
    notice = db.get(Announcement, announcement_id)
    if notice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such announcement")
    rows = db.scalars(
        select(EmailOutbox)
        .where(EmailOutbox.related_type == "announcement", EmailOutbox.related_id == announcement_id)
        .order_by(EmailOutbox.status, EmailOutbox.id)
        .limit(DELIVERY_LIST)
    )
    return {
        "announcement_id": announcement_id,
        "delivery": _delivery(db, [announcement_id])[announcement_id],
        "emails": [
            {
                "intended_to": r.intended_to,
                "to": r.to_addr,
                "status": r.status,
                "attempts": r.attempts,
                "error": r.error,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            }
            for r in rows
        ],
    }


@router.post("/announcements/preview")
def preview_announcement(body: NoticeIn, ctx: AuthContext = Depends(admin_only), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Who would be reached and the email that would go to them; writes nothing."""
    result = REGISTRY.invoke("publish_notice", ctx, db, body.tool_args())
    db.rollback()
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])
    preview = dict(result["preview"])
    email = preview.pop("email_preview", None)
    return {"preview": preview, "email": email, "emailing": email is not None}


@router.post("/announcements", status_code=status.HTTP_201_CREATED)
def publish_announcement(
    body: NoticeIn,
    background: BackgroundTasks,
    ctx: AuthContext = Depends(admin_only),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    with collecting() as outbox_rows:
        result = run_action(db, ctx, "publish_notice", body.tool_args())
    # only once the notice and its outbox rows are committed; held rows are never sent
    background.add_task(flush_in_background, [r.id for r in outbox_rows if r.status == "queued"])
    return result


# --- dashboard -------------------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(ctx: AuthContext = Depends(admin_only), db: Session = Depends(get_db)) -> dict[str, Any]:
    me = identity_row(db, ctx)
    departments = read_tool("get_department_overview", ctx, db)
    attendance = read_tool("get_university_attendance_report", ctx, db)
    fees_by_dept = {r["dept"]: r for r in read_tool("get_fee_collection_summary", ctx, db)}

    tracked = sum(r["students"] for r in attendance)
    weighted = sum(r["average_percent"] * r["students"] for r in attendance if r["average_percent"] is not None)
    by_dept_att: dict[str, list[tuple[float, int]]] = {}
    for r in attendance:
        if r["average_percent"] is not None:
            by_dept_att.setdefault(r["dept"], []).append((r["average_percent"], r["students"]))

    billed = sum(r["billed"] for r in fees_by_dept.values())
    collected = sum(r["collected"] for r in fees_by_dept.values())
    rows = []
    for d in departments:
        att = by_dept_att.get(d["dept"], [])
        n = sum(s for _, s in att)
        fee = fees_by_dept.get(d["dept"], {})
        rows.append(
            {
                **d,
                "avg_attendance_percent": round(sum(a * s for a, s in att) / n, 1) if n else None,
                "below_attendance": sum(r["below_threshold"] for r in attendance if r["dept"] == d["dept"]),
                "fee_collection_percent": fee.get("collection_rate_percent"),
                "fee_outstanding": fee.get("outstanding"),
            }
        )
    return {
        "admin": {"full_name": me.full_name, "designation": me.designation},
        "term": ctx.term,
        "kpis": {
            "students": sum(d["students"] for d in departments),
            "faculty": sum(d["faculty"] for d in departments),
            "departments": len(departments),
            "avg_attendance_percent": round(weighted / tracked, 1) if tracked else None,
            "below_attendance": sum(r["below_threshold"] for r in attendance),
            "fees_billed": billed,
            "fees_collected": collected,
            "fees_outstanding": round(billed - collected, 2),
            "fee_collection_percent": round(collected * 100 / billed, 1) if billed else None,
        },
        "departments": rows,
        "recent_announcements": recent_notices(db, 5),
    }
