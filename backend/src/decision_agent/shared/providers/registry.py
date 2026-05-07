from __future__ import annotations

import os
from pathlib import Path

from decision_agent.settings import load_env_file
from decision_agent.shared.providers.base import LLMProvider

OLLAMA_MODEL_ALIASES = {
    "ollama/qwen2.5": "qwen2.5:7b-instruct",
    "ollama/llama3.1": "llama3.1:8b-instruct",
}


def get_provider(override: str | None = None) -> LLMProvider:
    """Return the configured provider.

    If `override` is set, it takes precedence (used by benchmark runs that
    sweep providers per-condition). Otherwise read MODEL_PROVIDER env var.
    Supported values:
      - anthropic
      - ollama, ollama/qwen2.5, ollama/llama3.1, ollama/<model-tag>
      - mock (default)
    """
    load_env_file(Path.cwd() / ".env")
    name = (override or os.environ.get("MODEL_PROVIDER", "mock")).lower().strip()

    if name == "anthropic":
        from decision_agent.shared.providers.anthropic import AnthropicProvider
        return AnthropicProvider()

    if name == "ollama" or name.startswith("ollama/") or name.startswith("ollama:"):
        from decision_agent.shared.providers.ollama import OllamaProvider
        if name in OLLAMA_MODEL_ALIASES:
            return OllamaProvider(model=OLLAMA_MODEL_ALIASES[name])
        if name == "ollama":
            return OllamaProvider()  # uses OLLAMA_MODEL env var
        # ollama/<custom-tag> or ollama:<custom-tag>
        sep = "/" if "/" in name else ":"
        custom = name.split(sep, 1)[1]
        return OllamaProvider(model=custom)

    from decision_agent.shared.providers.mock import MockProvider
    return MockProvider()
