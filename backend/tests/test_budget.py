"""Phase 2 step 4 — token budget, limiter and 429 backoff (plan.md §4).

Time is faked throughout: the clock only moves when the fake sleeper is called,
so a test covering a 30-second backoff still runs in microseconds.
"""
from __future__ import annotations

import pytest

from app.ai.budget import (
    BudgetedProvider,
    TokenBucket,
    backoff_delay,
    estimate_tokens,
    queued_notifier,
    with_backoff,
)
from app.ai.providers.base import LLMResponse, ProviderError, ProviderRateLimited, Usage


class Clock:
    """A monotonic clock that only advances when something sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


MAX_JITTER = lambda lo, hi: hi  # noqa: E731 - deterministic "worst case" jitter
NO_JITTER = lambda lo, hi: lo  # noqa: E731


def bucket(rate_per_min=600.0, **kw) -> tuple[TokenBucket, Clock]:
    clock = Clock()
    return TokenBucket(rate_per_min, clock=clock, sleeper=clock.sleep, **kw), clock


# --- the bucket -------------------------------------------------------------

def test_take_within_capacity_does_not_wait():
    b, clock = bucket(600)  # 600/min = 10/sec, capacity 600
    assert b.take(100) == 0.0
    assert b.level == pytest.approx(500)
    assert clock.slept == []


def test_take_beyond_capacity_waits_for_the_refill():
    b, clock = bucket(600)
    b.take(600)  # drained
    waited = b.take(100)
    assert waited == pytest.approx(10.0)  # 100 tokens at 10/sec
    assert clock.slept == [pytest.approx(10.0)]


def test_bucket_refills_over_time_and_stops_at_capacity():
    b, clock = bucket(600)
    b.take(600)
    clock.advance(30)
    assert b.level == pytest.approx(300)
    clock.advance(600)
    assert b.level == pytest.approx(600)  # never more than capacity


def test_a_request_larger_than_the_bucket_is_clamped_not_deadlocked():
    b, _ = bucket(600)
    assert b.take(10_000) == 0.0  # clamped to capacity, which is available
    assert b.level == pytest.approx(0)


def test_charge_can_overdraw_and_the_next_caller_pays_for_it():
    b, clock = bucket(600)
    b.charge(900)  # an under-estimate trued up after the fact
    assert b.level == pytest.approx(-300)
    waited = b.take(100)
    assert waited == pytest.approx(40.0)  # 300 to get back to zero, then 100 more


def test_refund_returns_an_over_estimate():
    b, _ = bucket(600)
    b.take(500)
    b.refund(200)
    assert b.level == pytest.approx(300)


# --- estimation -------------------------------------------------------------

def test_estimate_grows_with_prompt_tools_and_reserves_output():
    small = estimate_tokens(system="hi", messages=[], max_tokens=100)
    assert small >= 100  # the output allowance is reserved up front

    with_history = estimate_tokens(
        system="hi", messages=[{"role": "user", "content": "x" * 400}], max_tokens=100
    )
    assert with_history >= small + 100  # 400 chars ~ 100 tokens

    with_tools = estimate_tokens(
        system="hi",
        messages=[],
        tools=[{"type": "function", "function": {"name": "n" * 400}}],
        max_tokens=100,
    )
    assert with_tools > small


# --- backoff ----------------------------------------------------------------

def test_backoff_honours_the_servers_retry_after():
    assert backoff_delay(0, retry_after=2.5, rand=NO_JITTER) == pytest.approx(2.5)
    assert backoff_delay(0, retry_after=2.5, rand=MAX_JITTER) == pytest.approx(3.0)


def test_backoff_doubles_and_is_capped():
    delays = [backoff_delay(n, base=1.0, cap=30.0, rand=NO_JITTER) for n in range(8)]
    assert delays[:4] == [0.5, 1.0, 2.0, 4.0]  # equal jitter: half the window
    assert max(delays) == 15.0  # cap 30 -> 15 fixed + up to 15 random


def test_backoff_jitter_stays_inside_the_window():
    assert backoff_delay(3, base=1.0, cap=30.0, rand=MAX_JITTER) == pytest.approx(8.0)


def test_with_backoff_retries_a_429_then_succeeds():
    clock = Clock()
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ProviderRateLimited("429", retry_after=None)
        return "ok"

    assert with_backoff(flaky, sleeper=clock.sleep, rand=NO_JITTER) == "ok"
    assert clock.slept == [0.5, 1.0]  # it actually waited between attempts


def test_with_backoff_gives_up_and_reraises():
    clock = Clock()

    def always():
        raise ProviderRateLimited("429")

    with pytest.raises(ProviderRateLimited):
        with_backoff(always, max_retries=2, sleeper=clock.sleep, rand=NO_JITTER)
    assert len(clock.slept) == 2  # two waits, three attempts


def test_with_backoff_does_not_retry_other_provider_errors():
    calls = []

    def broken():
        calls.append(1)
        raise ProviderError("model does not exist")

    with pytest.raises(ProviderError):
        with_backoff(broken, sleeper=lambda s: None)
    assert len(calls) == 1


# --- the wrapper ------------------------------------------------------------

class FakeInner:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def chat(self, **kwargs) -> LLMResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else LLMResponse(text="ok")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def budgeted(*outcomes, tpm=6000, rpm=25) -> tuple[BudgetedProvider, FakeInner, Clock]:
    clock = Clock()
    inner = FakeInner(*outcomes)
    provider = BudgetedProvider(
        inner, tpm=tpm, rpm=rpm, clock=clock, sleeper=clock.sleep, rand=NO_JITTER
    )
    return provider, inner, clock


def test_every_argument_is_passed_through_untouched():
    provider, inner, _ = budgeted()
    provider.chat(
        system="s", messages=[{"role": "user", "content": "q"}], model="m",
        tools=[{"type": "function"}], reasoning_effort="medium", max_tokens=99,
        json_object=True,
    )
    sent = inner.calls[0]
    assert sent["model"] == "m"
    assert sent["reasoning_effort"] == "medium"
    assert sent["max_tokens"] == 99
    assert sent["json_object"] is True


def test_usage_is_metered_across_calls():
    provider, _, _ = budgeted(
        LLMResponse(usage=Usage(100, 20)), LLMResponse(usage=Usage(200, 30))
    )
    provider.chat(system="s", messages=[], model="m")
    provider.chat(system="s", messages=[], model="m")
    assert provider.meter.calls == 2
    assert provider.meter.usage == Usage(300, 50)


def test_an_underestimate_is_charged_back_to_the_bucket():
    provider, _, _ = budgeted(LLMResponse(usage=Usage(3000, 500)), tpm=6000)
    before = provider.tokens.level
    provider.chat(system="s", messages=[], model="m")
    # the estimate was a few hundred tokens; the bill was 3500, and the bucket
    # must reflect the bill, not the guess
    assert before - provider.tokens.level == pytest.approx(3500, abs=1)


def test_an_overestimate_is_refunded():
    provider, _, _ = budgeted(LLMResponse(usage=Usage(10, 5)), tpm=6000)
    before = provider.tokens.level
    provider.chat(system="s", messages=[], model="m", max_tokens=2000)
    assert before - provider.tokens.level == pytest.approx(15, abs=1)


def test_exhausting_the_budget_queues_rather_than_failing():
    seen: list[tuple[float, str]] = []
    provider, inner, clock = budgeted(
        LLMResponse(usage=Usage(600, 0)), LLMResponse(usage=Usage(10, 0)), tpm=600
    )
    with queued_notifier(lambda s, reason: seen.append((s, reason))):
        provider.chat(system="s", messages=[], model="m")  # drains the minute
        provider.chat(system="s", messages=[], model="m")  # must wait for refill

    assert len(inner.calls) == 2  # both calls happened; nothing was dropped
    assert clock.slept, "the second call should have waited for the bucket"
    assert seen and seen[0][1] == "token_budget"
    assert provider.meter.waited_seconds > 0


def test_a_429_is_absorbed_and_reported_as_queued():
    seen: list[tuple[float, str]] = []
    provider, inner, clock = budgeted(
        ProviderRateLimited("429", retry_after=4.0), LLMResponse(text="ok", usage=Usage(10, 5))
    )
    with queued_notifier(lambda s, reason: seen.append((s, reason))):
        out = provider.chat(system="s", messages=[], model="m")

    assert out.text == "ok"
    assert clock.slept == [pytest.approx(4.0)]  # the server's own retry-after
    assert ("rate_limited",) == tuple(r for _, r in seen)
    assert provider.meter.rate_limited == 0  # it recovered, so nothing to count


def test_a_429_that_outlives_its_retries_is_raised_and_counted():
    provider, _, _ = budgeted(*[ProviderRateLimited("429", retry_after=0.6)] * 5)
    provider.max_retries = 2
    with pytest.raises(ProviderRateLimited):
        provider.chat(system="s", messages=[], model="m")
    assert provider.meter.rate_limited == 1


def test_the_notifier_is_scoped_to_one_turn():
    seen: list[tuple[float, str]] = []
    with queued_notifier(lambda s, r: seen.append((s, r))):
        pass
    provider, _, _ = budgeted(ProviderRateLimited("429", retry_after=4.0), LLMResponse())
    provider.chat(system="s", messages=[], model="m")  # outside the context now
    assert seen == []


def test_a_broken_notifier_does_not_fail_the_turn():
    def explode(seconds: float, reason: str) -> None:
        raise RuntimeError("UI is gone")

    provider, _, _ = budgeted(ProviderRateLimited("429", retry_after=4.0), LLMResponse(text="ok"))
    with queued_notifier(explode):
        assert provider.chat(system="s", messages=[], model="m").text == "ok"


def test_short_waits_are_not_reported_as_queued():
    seen: list = []
    provider, _, _ = budgeted(ProviderRateLimited("429", retry_after=0.1), LLMResponse())
    with queued_notifier(lambda s, r: seen.append((s, r))):
        provider.chat(system="s", messages=[], model="m")
    assert seen == []  # a 0.1s blip is not worth a UI state change
