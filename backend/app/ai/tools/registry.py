"""Tool registry + the three RBAC enforcement layers (plan.md §5).

    Layer 1 — exposure:   REGISTRY.visible_to(role) filters tools BEFORE the LLM.
    Layer 2 — execution:   invoke() re-checks role; wrong role -> denied + audit.
    Layer 3 — identity:    caller-supplied identity args are dropped for non-admins
                           (decision='arg_stripped'); the tool reads identity from
                           AuthContext instead.

Every invocation writes an audit_log row in its own transaction so the record
survives even when the request transaction rolls back.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.auth.context import AuthContext, Role
from app.db.session import SessionLocal
from app.models import AuditLog

# args a client must never be trusted to set (an admin acting cross-user is the
# only exception, handled in invoke())
IDENTITY_ARGS = frozenset(
    {"student_id", "faculty_id", "admin_id", "user_id", "roll_no", "employee_id", "subject_ref"}
)


class Scope(str, Enum):
    SELF = "SELF"
    OWN_COURSES = "OWN_COURSES"
    OWN_DEPARTMENT = "OWN_DEPARTMENT"
    UNIVERSITY = "UNIVERSITY"


class ToolDenied(PermissionError):
    """Raised by Layer 2 when the caller's role may not use the tool."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., Any]
    allowed_roles: frozenset[Role]
    scope: Scope

    def visible_to(self, role: Role) -> bool:
        return role in self.allowed_roles


def _row_count(result: Any) -> int | None:
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict) and "rows" in result and isinstance(result["rows"], list):
        return len(result["rows"])
    return 1


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    # --- Layer 1 -------------------------------------------------------------
    def visible_to(self, role: Role) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.visible_to(role)]

    def index_for(self, role: Role) -> list[dict[str, str]]:
        """Compact name+description list for the router (Call A in Phase 2)."""
        return [{"name": t.name, "description": t.description} for t in self.visible_to(role)]

    # --- Layers 2 & 3 ------------------------------------------------------
    def invoke(
        self,
        name: str,
        ctx: AuthContext,
        db: Session,
        args: dict[str, Any] | None = None,
    ) -> Any:
        args = dict(args or {})
        spec = self._tools.get(name)

        if spec is None:
            _audit(ctx, name, args, "denied", None, 0)
            raise KeyError(f"unknown tool: {name}")

        # Layer 2 — execution guard
        if ctx.role not in spec.allowed_roles:
            _audit(ctx, name, args, "denied", None, 0)
            raise ToolDenied(f"{ctx.role.value} may not call {name}")

        # Layer 3 — identity args are never trusted (except admin acting cross-user)
        decision = "allowed"
        if ctx.role is not Role.ADMIN:
            stripped = {k: args.pop(k) for k in list(args) if k in IDENTITY_ARGS}
            if stripped:
                decision = "arg_stripped"

        started = time.perf_counter()
        result = spec.fn(ctx=ctx, db=db, **args)
        latency_ms = int((time.perf_counter() - started) * 1000)

        _audit(ctx, name, args, decision, _row_count(result), latency_ms)
        return result


REGISTRY = ToolRegistry()


def tool(
    *,
    name: str,
    description: str,
    allowed_roles: set[Role] | frozenset[Role],
    scope: Scope,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRY.register(
            ToolSpec(
                name=name,
                description=description,
                fn=fn,
                allowed_roles=frozenset(allowed_roles),
                scope=scope,
            )
        )
        return fn

    return deco


def _audit(
    ctx: AuthContext,
    tool_name: str,
    args: dict[str, Any],
    decision: str,
    rows_returned: int | None,
    latency_ms: int,
) -> None:
    with SessionLocal() as s:
        s.add(
            AuditLog(
                user_id=ctx.user_id,
                role=ctx.role.value,
                tool_name=tool_name,
                args=_jsonable(args),
                decision=decision,
                rows_returned=rows_returned,
                latency_ms=latency_ms,
            )
        )
        s.commit()


def _jsonable(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in args.items():
        out[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
    return out
