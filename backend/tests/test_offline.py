"""Step 6 guard: the suite must not depend on a live LLM.

CI runs with LLM_API_KEY unset. If a future test reaches the real provider it
fails loudly there, but this test makes the property explicit and local: with
no key, the process-wide budgeted provider refuses at construction, before any
network — so nothing in the suite can have silently used a real key.
"""
from __future__ import annotations

import pytest

from app.ai import budget, providers
from app.ai.providers.base import ProviderNotConfigured
from app.config import settings


def test_no_key_means_no_provider_at_all(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(budget, "_default", None)  # force a fresh lazy build
    providers.get_provider.cache_clear()
    try:
        with pytest.raises(ProviderNotConfigured):
            budget.get_budgeted_provider()
        assert budget._default is None  # nothing half-built was cached
    finally:
        providers.get_provider.cache_clear()
