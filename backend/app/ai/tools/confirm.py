"""Signed confirmation tokens for action tools (plan.md §7).

An action tool never writes on the model's say-so. Its first invocation
validates, builds a preview, and returns

    {"needs_confirmation": True, "preview": {...}, "token": "<payload>.<sig>"}

The token is an HMAC-SHA256 over `(user_id, tool, canonical args, exp, nonce)`.
POST /api/chat/confirm hands it back; `verify` recovers exactly the tool and
arguments the user saw in the preview — nothing about the call can be changed
between preview and execution, the token cannot be replayed (single-use nonce)
and it dies after `settings.confirm_token_ttl_seconds`.

The key is derived from the JWT secret with a domain separator, so an access
token and a confirm token can never be mistaken for one another even though
both are HMAC-signed with material from the same setting.

The used-nonce set is in-process. A restart forgets it, which re-opens a
replay window of at most one TTL; every action tool also re-validates on
execution (overlapping leave, attendance already marked, ...) so a replayed
write is refused on its own merits too.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.auth.context import AuthContext
from app.config import settings

_DOMAIN = b"uniassist-confirm-v1"


class ConfirmError(ValueError):
    """Base: the token cannot be honoured."""


class TokenInvalid(ConfirmError):
    """Malformed, tampered, or issued to a different user."""


class TokenExpired(ConfirmError):
    pass


class TokenUsed(ConfirmError):
    """Already executed once; the write it authorised must not happen twice."""


def _key() -> bytes:
    return hmac.new(settings.jwt_secret.encode(), _DOMAIN, hashlib.sha256).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical(args: dict[str, Any]) -> str:
    """One byte-for-byte representation per argument set, whatever the dict order."""
    return json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sign(*, user_id: int, tool: str, args: dict[str, Any], now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = {
        "u": user_id,
        "t": tool,
        "a": canonical(args),
        "exp": int(now) + settings.confirm_token_ttl_seconds,
        "n": secrets.token_urlsafe(12),
    }
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str, *, user_id: int, now: float | None = None) -> tuple[str, dict[str, Any]]:
    """Return `(tool, args)` for a valid, unexpired, unused token bound to `user_id`.

    Does NOT mark the token used — call `consume` once the write has committed,
    so a failed execution leaves the token honourable for a retry.
    """
    now = time.time() if now is None else now
    body, _, sig = token.partition(".")
    if not body or not sig:
        raise TokenInvalid("malformed token")
    expected = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise TokenInvalid("bad signature")
    try:
        payload = json.loads(_unb64(body))
        args = json.loads(payload["a"])
        tool, exp, nonce = payload["t"], int(payload["exp"]), payload["n"]
        if payload["u"] != user_id or not isinstance(args, dict) or not isinstance(tool, str):
            raise TokenInvalid("token was issued to someone else")
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenInvalid("malformed token") from exc
    if now >= exp:
        raise TokenExpired("confirmation window closed")
    _prune(now)
    if nonce in _used:
        raise TokenUsed("already confirmed")
    return tool, args


def consume(token: str) -> None:
    """Retire a token after its action committed. Idempotent."""
    body, _, _ = token.partition(".")
    try:
        payload = json.loads(_unb64(body))
        _used[payload["n"]] = int(payload["exp"])
    except (ValueError, KeyError, TypeError):  # verify() already vouched for it
        pass


_used: dict[str, int] = {}  # nonce -> exp; entries drop once they'd be expired anyway


def _prune(now: float) -> None:
    for nonce in [n for n, exp in _used.items() if exp <= now]:
        del _used[nonce]


def pending(ctx: AuthContext, tool: str, args: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    """What an action tool returns instead of writing: the orchestrator stops the turn here."""
    return {
        "needs_confirmation": True,
        "preview": preview,
        "token": sign(user_id=ctx.user_id, tool=tool, args=args),
    }
