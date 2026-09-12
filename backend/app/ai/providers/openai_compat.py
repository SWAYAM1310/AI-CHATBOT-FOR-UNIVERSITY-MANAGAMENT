"""OpenAI-compatible chat provider — Groq by default (plan.md §3).

Groq speaks the OpenAI wire format at https://api.groq.com/openai/v1, so this one
class also covers OpenRouter, Cerebras, Together and a local vLLM/Ollama; only
LLM_BASE_URL and the LLM_MODEL_* ids change.
"""
from __future__ import annotations

import ast
import json
import logging
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


log = logging.getLogger(__name__)

NO_TOOLS_NOTE = (
    "\n\nThere are no tools in this step. Do not emit a tool or function call of any kind; "
    "write your reply as plain text in the format asked for above."
)

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

        return self._create(payload)

    def _create(self, payload: dict[str, Any]) -> LLMResponse:
        try:
            return _to_response(
                self._client.chat.completions.create(**{k: v for k, v in payload.items() if not k.startswith("_")})
            )
        except openai.RateLimitError as exc:
            raise ProviderRateLimited(str(exc), retry_after=_retry_after(exc)) from exc
        except openai.BadRequestError as exc:
            # portability: not every OpenAI-compatible backend knows reasoning_effort
            reason = _error_text(exc)
            if "reasoning_effort" in payload and "reasoning_effort" in reason:
                payload.pop("reasoning_effort")
                return self._create(payload)
            # gpt-oss on Groq sometimes "calls a tool" in a step that has none attached
            # (the router, or the final answer); Groq rejects the whole response with
            # 400 tool_use_failed. It is random per phrasing: say it plainly and retry once.
            if "tool_use_failed" in reason and "tools" not in payload:
                if not payload.get("_no_tools_retry"):
                    log.warning("model called a tool in a no-tools step (%s); retrying with a plain-text note", payload["model"])
                    retry = dict(payload)
                    retry["_no_tools_retry"] = True
                    retry["messages"] = [
                        {**payload["messages"][0], "content": payload["messages"][0]["content"] + NO_TOOLS_NOTE},
                        *payload["messages"][1:],
                    ]
                    return self._create(retry)
                # it insisted (temperature 0 makes the retry near-deterministic). Groq returns the
                # rejected generation: hand the call the model wanted to the orchestrator, which
                # knows what to do with a tool name - the provider would only have a 502 to offer.
                salvaged = _salvage_tool_call(_failed_generation(exc), payload["model"])
                if salvaged is not None:
                    log.warning("model insisted on %s in a no-tools step; passing the call up", salvaged.tool_calls[0].name)
                    return salvaged
            if ("json_validate_failed" in reason or "output_parse_failed" in reason) and (
                "response_format" in payload or payload.get("_json_retry")
            ):
                # json_object mode, but the model answered in prose (a refusal, or a thought like
                # "Need academic calendar."). The prompt asks for JSON anyway and parse_json_object()
                # tolerates prose around it: ask once more without the strict mode
                if not payload.get("_json_retry"):
                    log.warning("model broke JSON mode (%s); retrying without response_format", payload["model"])
                    retry = {k: v for k, v in payload.items() if k != "response_format"}
                    retry["_json_retry"] = True
                    return self._create(retry)
                text = _failed_generation(exc)
                if text:
                    log.warning("model wrote prose in a JSON step (%s); using it as the reply", payload["model"])
                    return LLMResponse(text=text, model=payload["model"], finish_reason="json_validate_failed")
            raise ProviderError(str(exc)) from exc
        except openai.APIError as exc:  # connection, timeout, 5xx, ...
            raise ProviderError(str(exc)) from exc


def _error_text(exc: Exception) -> str:
    """The message plus the body: the SDK puts Groq's error code in one or the other."""
    body = getattr(exc, "body", None)
    return f"{exc} {json.dumps(body) if isinstance(body, dict) else ''}"


def _failed_generation(exc: Exception) -> str:
    """Groq's 400s carry the generation it rejected, in the body or (older SDKs) only in the message."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict) and isinstance(err.get("failed_generation"), str):
            return err["failed_generation"]
    # the SDK's message is "Error code: 400 - <python repr of the body>"
    _, _, tail = str(exc).partition(" - ")
    try:
        parsed = ast.literal_eval(tail.strip())
    except (ValueError, SyntaxError):
        return ""
    err = parsed.get("error", parsed) if isinstance(parsed, dict) else None
    gen = err.get("failed_generation") if isinstance(err, dict) else None
    return gen if isinstance(gen, str) else ""


def _salvage_tool_call(generation: str, model: str) -> LLMResponse | None:
    """`{"name": "tool.get_my_fees", "arguments": {...}}` -> a response carrying that ToolCall."""
    try:
        parsed = json.loads(generation)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("name"), str):
        return None
    name = parsed["name"].rsplit(".", 1)[-1]  # gpt-oss namespaces it: "tool.x", "functions.x"
    if not name:
        return None
    return LLMResponse(
        tool_calls=[ToolCall(id="salvaged", name=name, arguments=_json_args(parsed.get("arguments")))],
        model=model,
        finish_reason="tool_calls",
    )


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
