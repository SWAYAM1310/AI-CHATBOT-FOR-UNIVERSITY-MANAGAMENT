"""Deterministic bodies for leave notifications.

This is the fallback when LLM drafting is off, unavailable, or fails
(app/notify/draft.py) — a leave application or decision must never be
delayed, or blocked, by the model that would merely word its email.
"""
from __future__ import annotations


def leave_applied_subject(roll_no: str, from_date: str, to_date: str) -> str:
    return f"[UniAssist] Leave application {roll_no} — {from_date} to {to_date}"


def leave_applied_body(
    *,
    full_name: str,
    roll_no: str,
    from_date: str,
    to_date: str,
    days: int,
    reason: str,
    approver: str | None,
) -> str:
    greeting = approver or "Head of Department"
    return (
        f"Dear {greeting},\n\n"
        f"{full_name} ({roll_no}) has applied for {days} day(s) of leave, "
        f"from {from_date} to {to_date}.\n\n"
        f"Reason: {reason}\n\n"
        f"Please review this request in UniAssist.\n\n"
        f"— UniAssist"
    )


def leave_decided_subject(roll_no: str, decision: str) -> str:
    return f"[UniAssist] Leave request {decision} — {roll_no}"


def leave_decided_body(
    *,
    full_name: str,
    from_date: str,
    to_date: str,
    decision: str,
    decided_by: str | None,
) -> str:
    by = f" by {decided_by}" if decided_by else ""
    return (
        f"Dear {full_name},\n\n"
        f"Your leave request for {from_date} to {to_date} has been {decision}{by}.\n\n"
        f"— UniAssist"
    )


def announcement_subject(title: str) -> str:
    return f"[UniAssist] {title}"


def announcement_body(*, title: str, body: str, audience_label: str, issued_by: str | None) -> str:
    sign = f"{issued_by}, UniAssist" if issued_by else "UniAssist"
    return (
        f"Dear {audience_label},\n\n"
        f"{title}\n\n"
        f"{body}\n\n"
        f"— {sign}"
    )
