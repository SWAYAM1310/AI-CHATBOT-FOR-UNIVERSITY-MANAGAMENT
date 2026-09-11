"""Typed, RBAC-guarded database tools.

The full ~35-tool catalog is Phase 2 (plan.md §6). This package holds the
registry machinery (app.ai.tools.registry) plus the tool modules, grouped by
who they're for: app.ai.tools.builtin (Phase-1b starter set), .student_tools
(student SELF reads), .shared_tools (all-role reads). Faculty and admin
catalogs, plus the two-phase-confirm action tools, land alongside the
orchestrator later in Phase 2.
"""
from __future__ import annotations

from app.ai.tools import builtin  # noqa: F401  - registers tools on import
from app.ai.tools import shared_tools  # noqa: F401  - registers tools on import
from app.ai.tools import student_tools  # noqa: F401  - registers tools on import
from app.ai.tools.registry import REGISTRY, Scope, tool

__all__ = ["REGISTRY", "Scope", "tool"]
