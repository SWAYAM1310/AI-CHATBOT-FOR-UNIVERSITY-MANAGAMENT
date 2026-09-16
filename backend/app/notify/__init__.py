"""Agentic email notifications — leave apply/decide (phase 1).

    transport.py  — where a message actually goes: console log, in-memory
                    (tests), or real SMTP (local Mailpit or a live provider).
    templates.py  — deterministic bodies; the fallback and the shape drafting fills.
    draft.py      — best-effort LLM drafting of the body, isolated for tests.
    mailer.py     — the outbox: queue_email() in the caller's transaction,
                    flush_outbox() after it commits (app/api/chat.py).

Mirrors app/ai/providers: a small Protocol plus a real implementation and test
doubles, so nothing downstream needs to know which transport is wired in.
"""
from __future__ import annotations
