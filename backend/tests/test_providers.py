"""Phase 2 step 2 — the OpenAI-compatible provider (plan.md §3).

No network and no API key: a fake client stands in for the SDK, so this suite
runs in CI exactly as it does on a machine with a live Groq key.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx2  # the transport openai>=3 ships with; used only to build error responses
import openai
import pytest

from app.ai.providers import (
    OpenAICompatProvider,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    Usage,
    parse_json_object,
)
from app.ai.providers.openai_compat import settings

REQ = httpx2.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
MAIN = "openai/gpt-oss-120b"


# --- fakes ------------------------------------------------------------------

def fake_reply(
    *,
    content: str | None = "hello",
    tool_calls: list | None = None,
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
    finish_reason: str = "stop",
    reasoning: str | None = None,
) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls, reasoning=reasoning)
    return SimpleNamespace(
        model=MAIN,
        choices=[SimpleNamespace(finish_reason=finish_reason, message=message)],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def fake_tool_call(name: str = "get_my_attendance", arguments: str = '{"course": "24CS201T"}'):
    return SimpleNamespace(id="call_1", function=SimpleNamespace(name=name, arguments=arguments))


class FakeCompletions:
    def __init__(self, outcomes: tuple) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else fake_reply()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, *outcomes) -> None:
        self.completions = FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


def make_provider(*outcomes) -> tuple[OpenAICompatProvider, FakeClient]:
    client = FakeClient(*outcomes)
    return OpenAICompatProvider(client=client), client


def rate_limit_error(retry_after: str | None = "2.5") -> openai.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return openai.RateLimitError(
        "429 rate limit reached", response=httpx2.Response(429, headers=headers, request=REQ), body=None
    )


def bad_request(message: str) -> openai.BadRequestError:
    return openai.BadRequestError(message, response=httpx2.Response(400, request=REQ), body=None)


# --- request shaping --------------------------------------------------------

def test_system_prompt_is_prepended_to_history():
    provider, client = make_provider()
    provider.chat(
        system="You are UniAssist.",
        messages=[{"role": "user", "content": "how is my attendance?"}],
        model=MAIN,
    )
    sent = client.completions.calls[0]
    assert sent["model"] == MAIN
    assert sent["messages"][0] == {"role": "system", "content": "You are UniAssist."}
    assert sent["messages"][1]["content"] == "how is my attendance?"


def test_caller_messages_are_not_mutated():
    provider, _ = make_provider()
    history = [{"role": "user", "content": "hi"}]
    provider.chat(system="s", messages=history, model=MAIN)
    assert history == [{"role": "user", "content": "hi"}]


def test_tools_enable_auto_tool_choice_and_are_omitted_when_absent():
    schema = {"type": "function", "function": {"name": "get_my_fees", "parameters": {}}}
    provider, client = make_provider(fake_reply(), fake_reply())

    provider.chat(system="s", messages=[], model=MAIN, tools=[schema])
    provider.chat(system="s", messages=[], model=MAIN)

    with_tools, without_tools = client.completions.calls
    assert with_tools["tools"] == [schema]
    assert with_tools["tool_choice"] == "auto"
    assert "tools" not in without_tools
    assert "tool_choice" not in without_tools


def test_json_object_and_max_tokens_map_to_wire_params():
    provider, client = make_provider()
    provider.chat(system="s", messages=[], model=MAIN, json_object=True, max_tokens=256)
    sent = client.completions.calls[0]
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["max_completion_tokens"] == 256  # Groq's current spelling; max_tokens is deprecated


def test_reasoning_effort_is_sent_by_default_and_omitted_when_none():
    provider, client = make_provider(fake_reply(), fake_reply())
    provider.chat(system="s", messages=[], model=MAIN)
    provider.chat(system="s", messages=[], model=MAIN, reasoning_effort=None)
    default_call, opted_out = client.completions.calls
    assert default_call["reasoning_effort"] == "low"
    assert "reasoning_effort" not in opted_out


# --- response parsing -------------------------------------------------------

def test_text_usage_and_metadata_are_captured():
    provider, _ = make_provider(fake_reply(content="you're at 68%", reasoning="checked records"))
    out = provider.chat(system="s", messages=[], model=MAIN)
    assert out.text == "you're at 68%"
    assert out.usage == Usage(tokens_in=11, tokens_out=7)
    assert out.usage.total == 18
    assert out.model == MAIN
    assert out.finish_reason == "stop"
    assert out.reasoning == "checked records"


def test_tool_calls_are_parsed_into_typed_calls():
    provider, _ = make_provider(fake_reply(content=None, tool_calls=[fake_tool_call()]))
    out = provider.chat(system="s", messages=[], model=MAIN)
    assert out.text == ""  # a pure tool-call turn has no content
    assert len(out.tool_calls) == 1
    call = out.tool_calls[0]
    assert (call.id, call.name) == ("call_1", "get_my_attendance")
    assert call.arguments == {"course": "24CS201T"}


def test_malformed_tool_arguments_degrade_to_empty_dict():
    provider, _ = make_provider(fake_reply(tool_calls=[fake_tool_call(arguments="{not json")]))
    out = provider.chat(system="s", messages=[], model=MAIN)
    assert out.tool_calls[0].arguments == {}


def test_missing_usage_block_is_tolerated():
    reply = fake_reply()
    reply.usage = None
    provider, _ = make_provider(reply)
    assert provider.chat(system="s", messages=[], model=MAIN).usage == Usage(0, 0)


# --- error mapping ----------------------------------------------------------

def test_rate_limit_maps_to_provider_rate_limited_with_retry_hint():
    provider, _ = make_provider(rate_limit_error("2.5"))
    with pytest.raises(ProviderRateLimited) as exc:
        provider.chat(system="s", messages=[], model=MAIN)
    assert exc.value.retry_after == 2.5


def test_rate_limit_without_header_has_no_retry_hint():
    provider, _ = make_provider(rate_limit_error(None))
    with pytest.raises(ProviderRateLimited) as exc:
        provider.chat(system="s", messages=[], model=MAIN)
    assert exc.value.retry_after is None


def test_connection_failure_maps_to_provider_error():
    provider, _ = make_provider(openai.APIConnectionError(request=REQ))
    with pytest.raises(ProviderError):
        provider.chat(system="s", messages=[], model=MAIN)


def test_backend_that_rejects_reasoning_effort_is_retried_without_it():
    """Portability: a local Ollama/vLLM may not know the param (plan.md §4 fallback)."""
    provider, client = make_provider(bad_request("unknown parameter: 'reasoning_effort'"), fake_reply())
    out = provider.chat(system="s", messages=[], model=MAIN)
    assert out.text == "hello"
    first, retry = client.completions.calls
    assert first["reasoning_effort"] == "low"
    assert "reasoning_effort" not in retry


GROQ_TOOL_USE_FAILED = (
    "Error code: 400 - {'error': {'message': 'Tool choice is none, but model called a tool', "
    "'type': 'invalid_request_error', 'code': 'tool_use_failed', 'failed_generation': '{\"name\": \"router\"'}}"
)


def test_a_phantom_tool_call_in_a_no_tools_step_is_retried_once_with_a_plain_text_note():
    """gpt-oss on Groq: the router/answer step 'calls a tool' that is not attached -> 400 tool_use_failed."""
    from app.ai.providers.openai_compat import NO_TOOLS_NOTE

    provider, client = make_provider(bad_request(GROQ_TOOL_USE_FAILED), fake_reply())
    out = provider.chat(system="You are the ROUTER.", messages=[{"role": "user", "content": "hi"}], model=MAIN, json_object=True)
    assert out.text == "hello"
    first, retry = client.completions.calls
    assert first["messages"][0]["content"] == "You are the ROUTER."
    assert retry["messages"][0]["content"] == "You are the ROUTER." + NO_TOOLS_NOTE
    assert retry["messages"][1:] == first["messages"][1:] and "_no_tools_retry" not in retry

    # a second failure is not retried again; and a step that HAS tools is not retried at all
    provider, client = make_provider(bad_request(GROQ_TOOL_USE_FAILED), bad_request(GROQ_TOOL_USE_FAILED))
    with pytest.raises(ProviderError):
        provider.chat(system="s", messages=[], model=MAIN)
    assert len(client.completions.calls) == 2
    provider, client = make_provider(bad_request(GROQ_TOOL_USE_FAILED))
    with pytest.raises(ProviderError):
        provider.chat(system="s", messages=[], model=MAIN, tools=[{"type": "function", "function": {"name": "t"}}])
    assert len(client.completions.calls) == 1


def test_other_bad_requests_are_not_retried():
    provider, client = make_provider(bad_request("model `nope` does not exist"))
    with pytest.raises(ProviderError):
        provider.chat(system="s", messages=[], model="nope")
    assert len(client.completions.calls) == 1


def test_missing_api_key_raises_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(ProviderNotConfigured):
        OpenAICompatProvider()


# --- JSON helper used by Calls A and B --------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        '{"intent": "attendance", "needs_rag": true}',
        '```json\n{"intent": "attendance", "needs_rag": true}\n```',
        'Sure! {"intent": "attendance", "needs_rag": true} hope that helps',
    ],
)
def test_parse_json_object_recovers_wrapped_replies(raw):
    assert parse_json_object(raw) == {"intent": "attendance", "needs_rag": True}


@pytest.mark.parametrize("raw", ["", "no json here", "[1, 2, 3]"])
def test_parse_json_object_returns_empty_dict_instead_of_raising(raw):
    assert parse_json_object(raw) == {}
