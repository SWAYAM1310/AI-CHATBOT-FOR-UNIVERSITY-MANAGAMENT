"""Caller-scoped endpoints. Demonstrates AuthContext + RBAC layer 1 (tool exposure)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.tools.registry import REGISTRY
from app.auth.context import AuthContext, Role
from app.auth.deps import get_auth_context, get_db

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def me(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = None
    if ctx.role in (Role.STUDENT, Role.FACULTY):
        profile = REGISTRY.invoke("get_my_profile", ctx, db)
    return {
        "user_id": ctx.user_id,
        "role": ctx.role.value,
        "subject_ref": ctx.subject_ref,
        "dept_id": ctx.dept_id,
        "is_hod": ctx.is_hod,
        "term": ctx.term,
        "profile": profile,
    }


@router.get("/me/tools")
def my_tools(ctx: AuthContext = Depends(get_auth_context)) -> list[dict[str, str]]:
    """The tool index this caller's role is allowed to see (RBAC layer 1)."""
    return REGISTRY.index_for(ctx.role)
