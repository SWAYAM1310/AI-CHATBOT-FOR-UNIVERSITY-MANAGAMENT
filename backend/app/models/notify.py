"""Outbox for agentic email notifications (leave apply/decide, phase 1).

Written in the same transaction as the record it notifies about, so a rolled-
back action can never have queued an email; flushed by the confirm endpoint
only after that transaction's commit (app/api/chat.py), so a send failure can
never lose the underlying write. `idempotency_key` carries a unique index so a
replayed confirm token cannot double-send.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    to_addr = Column(String, nullable=False)  # actual SMTP envelope recipient (post-redirect)
    intended_to = Column(String, nullable=False)  # the synthetic address this was really for
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    related_type = Column(String, nullable=False)  # "leave_request"
    related_id = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="queued")  # queued|sent|failed|suppressed
    attempts = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    sent_at = Column(DateTime(timezone=True), nullable=True)
