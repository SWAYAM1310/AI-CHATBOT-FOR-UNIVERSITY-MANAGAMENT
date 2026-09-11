"""Provider-agnostic LLM interface (plan.md §3).

The orchestrator talks only to this Protocol, so swapping Groq for OpenRouter,
Cerebras, Together or a local vLLM/Ollama is a base-URL + model-name change —
which is exactly the offline fallback plan.md §4 wants ready before demo day.
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict

MsgRole = Literal["system", "user", "assistant", "tool"]


class Msg(TypedDict, total=False):
    """One wire-format chat message.

    `role` + `content` is the common case; `tool_calls` (on an assistant turn)
    and `tool_call_id` (on a tool turn) carry a tool round-trip back to the model.
    """

    role: MsgRole
    content: str
    name: str
    tool_calls: list[dict[str, Any]]
    tool_call_id: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]  # JSON-parsed; {} when the model emitted garbage


@dataclass(frozen=True)
class Usage:
    """Token accounting for one call; summed per turn into messages.tokens_in/out."""

    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.tokens_in + other.tokens_in, self.tokens_out + other.tokens_out)


@dataclass(frozen=True)
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""
    reasoning: str | None = None  # gpt-oss returns its chain separately; for logs only


class ProviderError(RuntimeError):
    """Any provider-side failure the orchestrator should surface, not retry blindly."""


class ProviderNotConfigured(ProviderError):
    """No API key / unusable provider settings."""


class ProviderRateLimited(ProviderError):
    """HTTP 429. `retry_after` is the provider's hint, in seconds, when it sent one."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMProvider(Protocol):
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
    ) -> LLMResponse: ...


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_json_object(text: str) -> dict[str, Any]:
    """Best-effort JSON-object parse of a model reply (Calls A and B).

    Tolerates ```json fences and surrounding prose. Returns {} instead of raising:
    a malformed route reply should degrade to the fallback path, not 500 the turn.
    """
    if not text:
        return {}

    candidates = [text]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}
