"""LLM providers (plan.md §3). `get_provider()` is the orchestrator's entry point."""
from __future__ import annotations

from functools import lru_cache

from app.ai.providers.base import (
    LLMProvider,
    LLMResponse,
    Msg,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ToolCall,
    Usage,
    parse_json_object,
)
from app.ai.providers.openai_compat import OpenAICompatProvider


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    """The process-wide provider — one HTTP client, so connections are reused.

    Raises ProviderNotConfigured when LLM_API_KEY is unset, so this must be
    resolved per turn, never at import time: the app has to boot (and serve
    /health, /api/auth/login) on a machine with no key.
    """
    return OpenAICompatProvider()


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "Msg",
    "OpenAICompatProvider",
    "ProviderError",
    "ProviderNotConfigured",
    "ProviderRateLimited",
    "ToolCall",
    "Usage",
    "get_provider",
    "parse_json_object",
]
