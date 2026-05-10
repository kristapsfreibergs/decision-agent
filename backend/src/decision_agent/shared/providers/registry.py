from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from decision_agent.settings import load_env_file
from decision_agent.shared.providers.base import LLMProvider

OLLAMA_MODEL_ALIASES = {
    "ollama/qwen2.5": "qwen2.5:7b-instruct",
    "ollama/llama3.1": "llama3.1:8b-instruct",
}

# ---------------------------------------------------------------------------
# Circuit breaker — per provider, per process
# ---------------------------------------------------------------------------

_CIRCUIT_LOCK = threading.Lock()
_CIRCUIT_STATE: dict[str, dict[str, Any]] = {}
_CIRCUIT_THRESHOLD = int(os.environ.get("PROVIDER_CIRCUIT_THRESHOLD", "3"))
_CIRCUIT_RESET_SECONDS = float(os.environ.get("PROVIDER_CIRCUIT_RESET_SECONDS", "60"))


def _circuit_key(provider_name: str) -> str:
    return provider_name.lower()


def _record_success(provider_name: str) -> None:
    key = _circuit_key(provider_name)
    with _CIRCUIT_LOCK:
        _CIRCUIT_STATE.pop(key, None)


def _record_failure(provider_name: str) -> bool:
    """Record a failure. Returns True if the circuit just opened."""
    key = _circuit_key(provider_name)
    with _CIRCUIT_LOCK:
        state = _CIRCUIT_STATE.setdefault(key, {"failures": 0, "open_until": 0.0})
        state["failures"] += 1
        if state["failures"] >= _CIRCUIT_THRESHOLD and state["open_until"] <= time.monotonic():
            state["open_until"] = time.monotonic() + _CIRCUIT_RESET_SECONDS
            return True
    return False


def _circuit_is_open(provider_name: str) -> bool:
    key = _circuit_key(provider_name)
    with _CIRCUIT_LOCK:
        state = _CIRCUIT_STATE.get(key)
        if not state:
            return False
        if state["open_until"] <= time.monotonic():
            return False
        return state["failures"] >= _CIRCUIT_THRESHOLD


class ProviderCircuitOpenError(RuntimeError):
    """Raised when a provider circuit breaker is open (provider is down)."""


# ---------------------------------------------------------------------------
# FallbackProvider — tries primary, falls back to next on hard failure
# ---------------------------------------------------------------------------

class FallbackProvider(LLMProvider):
    """Tries providers in order. If primary fails (after its own retries),
    switches to the next. Emits no audit events itself — callers handle that.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackProvider requires at least one provider.")
        self._providers = providers

    @property
    def name(self) -> str:
        return f"fallback[{','.join(p.name for p in self._providers)}]"

    def _try_each(self, method: str, *args: Any, **kwargs: Any) -> Any:
        last_exc: BaseException | None = None
        for provider in self._providers:
            if _circuit_is_open(provider.name):
                last_exc = ProviderCircuitOpenError(f"Circuit open for {provider.name}")
                continue
            try:
                result = getattr(provider, method)(*args, **kwargs)
                _record_success(provider.name)
                return result
            except Exception as exc:
                opened = _record_failure(provider.name)
                last_exc = exc
                if opened:
                    # Circuit just opened — try next provider immediately
                    continue
                # Not yet open — re-raise for the current provider (retries already exhausted)
                continue
        raise last_exc or RuntimeError("All providers failed")

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        return self._try_each("complete", system, user, max_tokens=max_tokens)

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 4096,
        tool_choice: dict | None = None,
    ) -> dict:
        return self._try_each(
            "complete_with_tools", system, messages, tools,
            max_tokens=max_tokens, tool_choice=tool_choice,
        )


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def _build_single_provider(name: str) -> LLMProvider:
    if name == "anthropic":
        from decision_agent.shared.providers.anthropic import AnthropicProvider
        return AnthropicProvider()

    if name == "ollama" or name.startswith("ollama/") or name.startswith("ollama:"):
        from decision_agent.shared.providers.ollama import OllamaProvider
        if name in OLLAMA_MODEL_ALIASES:
            return OllamaProvider(model=OLLAMA_MODEL_ALIASES[name])
        if name == "ollama":
            return OllamaProvider()
        sep = "/" if "/" in name else ":"
        custom = name.split(sep, 1)[1]
        return OllamaProvider(model=custom)

    from decision_agent.shared.providers.mock import MockProvider
    return MockProvider()


def get_provider(override: str | None = None) -> LLMProvider:
    """Return the configured provider, wrapping with FallbackProvider when
    PROVIDER_FALLBACK is set.

    PROVIDER_FALLBACK is a comma-separated list of fallback provider names.
    Example:
        MODEL_PROVIDER=anthropic
        PROVIDER_FALLBACK=ollama/qwen2.5,mock

    If Anthropic fails after retries, the FallbackProvider tries Ollama, then Mock.
    Circuit breaker tracks consecutive failures per provider name and short-circuits
    after PROVIDER_CIRCUIT_THRESHOLD (default 3) consecutive failures for
    PROVIDER_CIRCUIT_RESET_SECONDS (default 60s).
    """
    load_env_file(Path.cwd() / ".env")
    primary_name = (override or os.environ.get("MODEL_PROVIDER", "mock")).lower().strip()
    primary = _build_single_provider(primary_name)

    fallback_raw = os.environ.get("PROVIDER_FALLBACK", "").strip()
    if not fallback_raw:
        return primary

    fallback_names = [n.strip().lower() for n in fallback_raw.split(",") if n.strip()]
    if not fallback_names:
        return primary

    fallbacks = [_build_single_provider(n) for n in fallback_names]
    return FallbackProvider([primary] + fallbacks)
