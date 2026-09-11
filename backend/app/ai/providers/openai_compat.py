"""OpenAI-compatible chat provider — Groq by default (plan.md §3).

Groq speaks the OpenAI wire format at https://api.groq.com/openai/v1, so this one
class also covers OpenRouter, Cerebras, Together and a local vLLM/Ollama; only
LLM_BASE_URL and the LLM_MODEL_* ids change.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import openai

from app.ai.providers.base import (
    LLMResponse,
    Msg,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ToolCall,
    Usage,
)
from app.config import settings


class OpenAICompatProvider:
    """Implements the LLMProvider Protocol against any OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> None:
        self.base_url = base_url or settings.llm_base_url

        if client is not None:  # tests inject a fake; no key needed
            self._client = client
            return

        key = settings.llm_api_key if api_key is None else api_key
        if not key:
            raise ProviderNotConfigured(
                "LLM_API_KEY is not set - put a Groq key in backend/.env before using the LLM path"
            )
        # max_retries=0 on purpose: retry/backoff with jitter is ours to own in
        # app/ai/budget.py (plan.md §4), where it feeds the UI's "queued" state.
        self._client = openai.OpenAI(
            base_url=self.base_url, api_key=key, timeout=timeout, max_retries=0
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
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, *(dict(m) for m in messages)],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        if json_object:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_completion_tokens"] = max_tokens
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort

        return _to_response(self._create(payload))

    def _create(self, payload: dict[str, Any]) -> Any:
        try:
            return self._client.chat.completions.create(**payload)
        except openai.RateLimitError as exc:
            raise ProviderRateLimited(str(exc), retry_after=_retry_after(exc)) from exc
        except openai.BadRequestError as exc:
            # portability: not every OpenAI-compatible backend knows reasoning_effort
            if "reasoning_effort" in payload and "reasoning_effort" in str(exc):
                payload.pop("reasoning_effort")
                return self._create(payload)
            raise ProviderError(str(exc)) from exc
        except openai.APIError as exc:  # connection, timeout, 5xx, ...
            raise ProviderError(str(exc)) from exc


def _retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _tool_calls(message: Any) -> list[ToolCall]:
    out: list[ToolCall] = []
    for call in getattr(message, "tool_calls", None) or []:
        fn = getattr(call, "function", None)
        out.append(
            ToolCall(
                id=getattr(call, "id", "") or "",
                name=getattr(fn, "name", "") or "",
                arguments=_json_args(getattr(fn, "arguments", None)),
            )
        )
    return out


def _json_args(raw: Any) -> dict[str, Any]:
    """Tool arguments arrive as a JSON string; a malformed one must not kill the turn."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_response(raw: Any) -> LLMResponse:
    choices = getattr(raw, "choices", None) or []
    choice = choices[0] if choices else None
    message = getattr(choice, "message", None)
    usage = getattr(raw, "usage", None)

    return LLMResponse(
        text=getattr(message, "content", None) or "",
        tool_calls=_tool_calls(message),
        usage=Usage(
            tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
            tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
        ),
        model=getattr(raw, "model", "") or "",
        finish_reason=getattr(choice, "finish_reason", "") or "",
        reasoning=getattr(message, "reasoning", None),
    )
