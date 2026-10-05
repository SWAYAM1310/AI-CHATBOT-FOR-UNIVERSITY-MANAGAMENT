"""How the website's REST endpoints reach the same logic the chatbot uses.

Writes go through `run_action`: the very action tools the assistant calls
(`mark_attendance`, `enter_marks`, ...), through `REGISTRY.invoke` so the role
check, identity stripping and audit row all still apply. The button click
stands in for the chat's confirm card, so the call is made with `confirmed=True`;
the tool validates everything before it looks at that flag, so a bad request is
refused exactly as it would be in chat.

Reads go through `read_tool`: the same functions, so the chat and a dashboard
can never disagree on a number, but without an audit row each. A dashboard
refreshes on a timer; an audit trail of its polling would bury the real
actions.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai.tools.registry import REGISTRY, ToolDenied
from app.auth.context import AuthContext


def read_tool(name: str, ctx: AuthContext, db: Session, **args: Any) -> Any:
    """Run a read-only tool for the caller, enforcing the same role gate as the registry."""
    spec = REGISTRY.get(name)
    if not spec.visible_to(ctx.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
    return spec.fn(ctx=ctx, db=db, **args)


def run_action(db: Session, ctx: AuthContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute an action tool as confirmed, commit it, and turn a refusal into an HTTP error."""
    try:
        result = REGISTRY.invoke(name, ctx, db, args, confirmed=True)
    except ToolDenied as exc:
        db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if isinstance(result, dict) and result.get("error"):
        db.rollback()
        message = str(result["error"])
        # "already recorded" / "already matches": the request is well-formed but conflicts with what exists
        code = status.HTTP_409_CONFLICT if "already" in message else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, message)
    db.commit()
    return result
