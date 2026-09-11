"""Token budget, rate limiting and 429 backoff (plan.md §4).

Free-tier survival is a first-class feature here, not a hack. Three pieces:

  TokenBucket      — a shared in-process limiter. Groq's limits are per
                     ORGANISATION, so every request from this process competes
                     for one ceiling; the bucket is process-wide, not per user.
  with_backoff     — exponential backoff with jitter on HTTP 429, honouring the
                     provider's retry-after hint when it sent one.
  BudgetedProvider — wraps any LLMProvider with both, plus the per-turn token
                     meter whose numbers land in messages.tokens_in/out.

Waiting is reported, never hidden: `queued_notifier` lets the API layer surface
a "queued" state in the UI instead of an error, which is the whole point of
absorbing a 429 rather than failing the turn.
"""
from __future__ import annotations

import contextvars
import json
import logging
import random
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.ai.providers import LLMProvider, LLMResponse, Msg, ProviderRateLimited, Usage, get_provider
from app.config import settings

log = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4  # close enough for a limiter; the real count comes back in usage
PER_MESSAGE_OVERHEAD = 16  # role/delimiter tokens the wire format adds per message
DEFAULT_OUTPUT_ALLOWANCE = 400  # TPM counts output too, so reserve some up front
NOTIFY_THRESHOLD = 0.5  # only tell the UI about a wait a human would notice


# --- the "queued" signal ----------------------------------------------------

Notifier = Callable[[float, str], None]

_notifier: contextvars.ContextVar[Notifier | None] = contextvars.ContextVar(
    "queued_notifier", default=None
)


@contextmanager
def queued_notifier(fn: Notifier) -> Iterator[None]:
    """Report waits for the duration of one turn.

    A ContextVar rather than an attribute because the provider is shared across
    every concurrent request, but the UI that needs the notice is one caller's.
    """
    token = _notifier.set(fn)
    try:
        yield
    finally:
        _notifier.reset(token)


def _notify(seconds: float, reason: str) -> None:
    fn = _notifier.get()
    if fn is not None and seconds >= NOTIFY_THRESHOLD:
        try:
            fn(seconds, reason)
        except Exception:  # noqa: BLE001 - a broken UI hook must not fail the turn
            log.exception("queued notifier raised")


# --- limiter ----------------------------------------------------------------

class TokenBucket:
    """Classic leaky bucket, thread-safe.

    Thread-safe matters: FastAPI runs sync endpoints in a worker threadpool, so
    several turns really do hit this at once.
    """

    def __init__(
        self,
        rate_per_min: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rate = rate_per_min / 60.0
        self.capacity = float(capacity if capacity is not None else rate_per_min)
        self._level = self.capacity
        self._clock = clock
        self._sleeper = sleeper
        self._updated = clock()
        self._lock = threading.Lock()

    @property
    def level(self) -> float:
        with self._lock:
            self._refill()
            return self._level

    def _refill(self) -> None:
        now = self._clock()
        self._level = min(self.capacity, self._level + (now - self._updated) * self.rate)
        self._updated = now

    def take(self, amount: float) -> float:
        """Block until `amount` is available. Returns the seconds spent waiting."""
        amount = min(float(amount), self.capacity)  # never ask for more than exists
        waited = 0.0
        while True:
            with self._lock:
                self._refill()
                if self._level >= amount:
                    self._level -= amount
                    return waited
                wait = (amount - self._level) / self.rate
            self._sleeper(wait)
            waited += wait

    def charge(self, amount: float) -> None:
        """Debit without waiting — used to true up an under-estimate after the fact.

        The level may go negative; that simply delays the next caller, which is
        the correct behaviour when we have already overspent the minute.
        """
        if amount <= 0:
            return
        with self._lock:
            self._refill()
            self._level -= float(amount)

    def refund(self, amount: float) -> None:
        if amount <= 0:
            return
        with self._lock:
            self._refill()
            self._level = min(self.capacity, self._level + float(amount))


# --- estimation -------------------------------------------------------------

def estimate_tokens(
    *,
    system: str,
    messages: Sequence[Msg],
    tools: Sequence[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
) -> int:
    """Pre-flight guess, deliberately generous — under-booking defeats the limiter."""
    chars = len(system or "")
    for m in messages:
        chars += len(str(m.get("content") or ""))
        if m.get("tool_calls"):
            chars += len(json.dumps(m["tool_calls"]))
    if tools:
        chars += len(json.dumps(list(tools)))

    return (
        chars // CHARS_PER_TOKEN
        + PER_MESSAGE_OVERHEAD * (len(messages) + 1)
        + (max_tokens or DEFAULT_OUTPUT_ALLOWANCE)
    )


# --- backoff ----------------------------------------------------------------

def backoff_delay(
    attempt: int,
    retry_after: float | None = None,
    *,
    base: float | None = None,
    cap: float | None = None,
    rand: Callable[[float, float], float] = random.uniform,
) -> float:
    """Equal-jitter backoff: half the window fixed, half random.

    Full jitter can retry almost immediately and re-trip the limit; no jitter
    makes concurrent callers retry in lockstep. This sits between the two.
    """
    base = settings.llm_backoff_base if base is None else base
    cap = settings.llm_backoff_cap if cap is None else cap

    if retry_after is not None and retry_after >= 0:
        # trust the server's number, plus a little so parallel callers spread out
        return min(cap, retry_after + rand(0.0, 0.5))

    window = min(cap, base * (2**attempt))
    return window / 2 + rand(0.0, window / 2)


def with_backoff(
    call: Callable[[], Any],
    *,
    max_retries: int | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    rand: Callable[[float, float], float] = random.uniform,
) -> Any:
    """Run `call`, retrying only ProviderRateLimited. Other errors surface at once."""
    max_retries = settings.llm_max_retries if max_retries is None else max_retries

    for attempt in range(max_retries + 1):
        try:
            return call()
        except ProviderRateLimited as exc:
            if attempt >= max_retries:
                log.warning("rate limited, out of retries after %d attempts", attempt + 1)
                raise
            delay = backoff_delay(attempt, exc.retry_after, rand=rand)
            log.info("rate limited; retrying in %.1fs (attempt %d)", delay, attempt + 1)
            _notify(delay, "rate_limited")
            sleeper(delay)

    raise AssertionError("unreachable")  # pragma: no cover


# --- meter ------------------------------------------------------------------

@dataclass
class Meter:
    """Running totals for the process — the per-turn numbers for the report."""

    calls: int = 0
    usage: Usage = Usage()
    waited_seconds: float = 0.0
    rate_limited: int = 0

    def record(self, usage: Usage) -> None:
        self.calls += 1
        self.usage = self.usage + usage


# --- the wrapper ------------------------------------------------------------

class BudgetedProvider:
    """An LLMProvider that queues instead of failing, and meters what it spends."""

    def __init__(
        self,
        inner: LLMProvider,
        *,
        tpm: int | None = None,
        rpm: int | None = None,
        max_retries: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        rand: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.inner = inner
        self.max_retries = settings.llm_max_retries if max_retries is None else max_retries
        self.meter = Meter()
        self._sleeper = sleeper
        self._rand = rand
        self.tokens = TokenBucket(
            tpm if tpm is not None else settings.llm_tpm, clock=clock, sleeper=sleeper
        )
        self.requests = TokenBucket(
            rpm if rpm is not None else settings.llm_rpm, clock=clock, sleeper=sleeper
        )

    def chat(
        self,
        *,
        system: str,
        messages: Sequence[Msg],
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        reasoning_effort: str | None = "low",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_object: bool = False,
    ) -> LLMResponse:
        estimate = estimate_tokens(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )
        waited = self.tokens.take(estimate) + self.requests.take(1)
        if waited:
            self.meter.waited_seconds += waited
            _notify(waited, "token_budget")

        def call() -> LLMResponse:
            return self.inner.chat(
                system=system,
                messages=messages,
                model=model,
                tools=tools,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
                max_tokens=max_tokens,
                json_object=json_object,
            )

        try:
            response = with_backoff(
                call, max_retries=self.max_retries, sleeper=self._sleeper, rand=self._rand
            )
        except ProviderRateLimited:
            self.meter.rate_limited += 1
            raise

        self._reconcile(estimate, response.usage)
        self.meter.record(response.usage)
        log.info(
            "llm %s est=%d actual=%d (in=%d out=%d)",
            model,
            estimate,
            response.usage.total,
            response.usage.tokens_in,
            response.usage.tokens_out,
        )
        return response

    def _reconcile(self, estimate: int, usage: Usage) -> None:
        """Settle the difference between the guess and what the provider billed."""
        actual = usage.total
        if not actual:
            return  # no usage block: keep the estimate as the charge
        self.tokens.charge(actual - estimate)
        self.tokens.refund(estimate - actual)


_default: BudgetedProvider | None = None
_default_lock = threading.Lock()


def get_budgeted_provider() -> BudgetedProvider:
    """The process-wide budgeted provider — one bucket shared by every turn.

    Built lazily, like get_provider(): it raises ProviderNotConfigured with no
    API key, and the app must still boot on a machine that has none.
    """
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = BudgetedProvider(get_provider())
    return _default
