from __future__ import annotations

import os

from decision_agent.shared.providers.base import LLMProvider


def get_provider() -> LLMProvider:
    """Return the configured provider based on MODEL_PROVIDER env var."""
    provider_name = os.environ.get("MODEL_PROVIDER", "mock").lower()

    if provider_name == "anthropic":
        from decision_agent.shared.providers.anthropic import AnthropicProvider
        return AnthropicProvider()

    from decision_agent.shared.providers.mock import MockProvider
    return MockProvider()
