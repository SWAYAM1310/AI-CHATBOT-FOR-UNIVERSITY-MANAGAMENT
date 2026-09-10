"""Typed, RBAC-guarded database tools.

The full ~35-tool catalog is Phase 2. This package currently holds the registry
machinery (app.ai.tools.registry) plus a small set of real tools that exercise
all three RBAC layers (app.ai.tools.builtin).
"""
from __future__ import annotations

from app.ai.tools import builtin  # noqa: F401  - registers tools on import
from app.ai.tools.registry import REGISTRY, Scope, tool

__all__ = ["REGISTRY", "Scope", "tool"]
