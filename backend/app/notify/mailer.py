"""The outbox: queue in the caller's transaction, send after it commits.

`queue_email()` is called from inside an action tool's `confirmed=True`
branch, in the same DB transaction as the row it is notifying about — so a
rolled-back leave application can never have queued an email. `flush_outbox()`
is called by the confirm endpoint (app/api/chat.py) only after that
transaction's `db.commit()`, so a send failure can never lose the write it was
notifying about; the row is simply left `failed` in the outbox.

Recipient safety: every synthetic address is fictitious, and a
`personal_email` can look exactly like a real Gmail/Outlook address. Two
independent guards apply, in order:

  1. EMAIL_REDIRECT_TO, if set, sends everything there regardless of recipient
     — the demo's one real inbox. The true address survives in the
     `X-UniAssist-Intended-To` header and a body banner.
  2. Otherwise, a recipient domain must be in EMAIL_ALLOWED_DOMAINS, or the
     configured SMTP host must be a local sandbox (Mailpit) — anything else is
     recorded `suppressed`, never sent, and never raises.
"""
from __future__ import annotations

import contextvars
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EmailOutbox
from app.notify.transport import get_transport, is_local_host


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# A request-scoped side channel so the confirm endpoint (app/api/chat.py) can
# flush exactly the rows a tool call just queued, without knowing which
# tool it was or which fields identify its rows. Mirrors
# app/ai/budget.py's queued_notifier ContextVar for the same reason: the
# registry that calls the tool is shared process-wide, but the list belongs
# to one caller's request.
_collector: contextvars.ContextVar[list[EmailOutbox] | None] = contextvars.ContextVar(
    "email_outbox_collector", default=None
)


@contextmanager
def collecting() -> Iterator[list[EmailOutbox]]:
    """Every row `queue_email()` writes inside this block, for the caller to
    `flush_outbox()` once its own transaction has committed.
    """
    rows: list[EmailOutbox] = []
    token = _collector.set(rows)
    try:
        yield rows
    finally:
        _collector.reset(token)


def _resolve_recipient(intended_to: str) -> tuple[str, str | None]:
    """(actual SMTP recipient, suppression reason or None)."""
    if settings.email_redirect_to:
        return settings.email_redirect_to, None
    domain = intended_to.rsplit("@", 1)[-1].lower()
    allowed = {d.strip().lower() for d in settings.email_allowed_domains.split(",") if d.strip()}
    if domain in allowed or is_local_host(settings.smtp_host):
        return intended_to, None
    return intended_to, f"recipient domain '{domain}' is not allowlisted and EMAIL_REDIRECT_TO is unset"


def _redirect_banner(intended_to: str) -> str:
    return f"--- DEMO REDIRECT — intended for {intended_to} ---\n\n"


def queue_email(
    db: Session,
    *,
    idempotency_key: str,
    to_addr: str,
    subject: str,
    body: str,
    related_type: str,
    related_id: int,
) -> EmailOutbox | None:
    """Write a queued (or suppressed) outbox row, or None if email is off, or
    an earlier attempt already queued this same `idempotency_key`.

    Does not send anything and does not commit — the caller's transaction
    owns that; call `flush_outbox()` after it commits.
    """
    if settings.email_mode == "off":
        return None

    existing = db.scalar(select(EmailOutbox.id).where(EmailOutbox.idempotency_key == idempotency_key))
    if existing:
        return None  # a replayed confirm must not queue a duplicate

    actual_to, suppress_reason = _resolve_recipient(to_addr)
    row = EmailOutbox(
        idempotency_key=idempotency_key,
        to_addr=actual_to,
        intended_to=to_addr,
        subject=subject,
        body=_redirect_banner(to_addr) + body if actual_to != to_addr else body,
        related_type=related_type,
        related_id=related_id,
        status="suppressed" if suppress_reason else "queued",
        attempts=0,
        error=suppress_reason,
    )
    db.add(row)
    db.flush()  # assigns row.id within the caller's still-open transaction

    collected = _collector.get()
    if collected is not None:
        collected.append(row)
    return row


def flush_outbox(db: Session, rows: Sequence[EmailOutbox]) -> None:
    """Actually send the rows this request queued, once their transaction is
    durable. Each row is committed independently: a failure sending row 2
    must not undo the successful send of row 1, or the leave write neither
    depends on.
    """
    transport = get_transport()
    for row in rows:
        if row is None or row.status != "queued":
            continue
        try:
            headers = (
                {"X-UniAssist-Intended-To": row.intended_to} if row.to_addr != row.intended_to else None
            )
            transport.send(
                from_addr=settings.email_from,
                to_addr=row.to_addr,
                subject=row.subject,
                body=row.body,
                headers=headers,
            )
            row.status = "sent"
            row.sent_at = _utcnow()
        except Exception as exc:  # noqa: BLE001 — never let a send failure raise past the outbox
            row.status = "failed"
            row.error = str(exc)[:500]
        row.attempts += 1
        db.commit()
