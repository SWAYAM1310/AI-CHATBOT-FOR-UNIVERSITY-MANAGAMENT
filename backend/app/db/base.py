"""Declarative base. All ORM models (added in the next part) inherit from this,
and Alembic autogenerate reads its metadata."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
