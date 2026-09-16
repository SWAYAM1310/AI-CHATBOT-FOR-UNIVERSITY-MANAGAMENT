"""Best-effort LLM drafting of a notification body — the agentic part.

Isolated behind one `draft()` function so tests can monkeypatch it without
touching the mailer or the tool that calls it. Drafting is opt-in
(settings.email_draft_enabled, off by default — see app/config.py) and never
allowed to block or fail a leave action: any provider error, or an empty
reply, falls back to the deterministic template in app/notify/templates.py.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from app.ai.budget import get_budgeted_provider
from app.ai.providers import ProviderError
from app.config import settings

log = logging.getLogger(__name__)

Kind = Literal["leave_applied", "leave_decided"]

_SYSTEM = (
    "You write short, professional email bodies for a university administration "
    "system. Reply with only the email body text: no subject line, no markdown, "
    "no placeholders, a formal but warm tone, under 120 words. Do not invent facts "
    "beyond what is given in the request."
)


def draft(kind: Kind, **ctx: Any) -> str | None:
    """A drafted body, or None if drafting is off, unavailable, or failed."""
    if not settings.email_draft_enabled:
        return None
    try:
        provider = get_budgeted_provider()
        reply = provider.chat(
            system=_SYSTEM,
            messages=[{"role": "user", "content": _prompt(kind, ctx)}],
            model=settings.llm_model_router,
            temperature=0.3,
            max_tokens=250,
        )
        text = (reply.text or "").strip()
        return text or None
    except ProviderError:
        log.info("email draft unavailable, falling back to template (kind=%s)", kind)
        return None
    except Exception:  # a drafting hiccup must never block the underlying action
        log.exception("email draft failed unexpectedly, falling back to template (kind=%s)", kind)
        return None


def _prompt(kind: Kind, ctx: dict[str, Any]) -> str:
    if kind == "leave_applied":
        approver = ctx["approver"] or "the Head of Department"
        return (
            f"Write an email to {approver} notifying them that {ctx['full_name']} "
            f"({ctx['roll_no']}) has applied for {ctx['days']} day(s) of leave, from "
            f"{ctx['from_date']} to {ctx['to_date']}, for the following reason: "
            f"\"{ctx['reason']}\". Ask them to review the request in UniAssist."
        )
    decided_by = ctx.get("decided_by")
    by_clause = f" by {decided_by}" if decided_by else ""
    return (
        f"Write an email to {ctx['full_name']}, a student, informing them that their "
        f"leave request for {ctx['from_date']} to {ctx['to_date']} has been "
        f"{ctx['decision']}{by_clause}."
    )
