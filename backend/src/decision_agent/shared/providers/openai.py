from __future__ import annotations

import json
import os
from typing import Any

from decision_agent.shared.providers.base import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT_SECONDS,
    LLMProvider,
)
from decision_agent.shared.providers.retry import with_retry


class OpenAIProvider(LLMProvider):
    """Calls OpenAI via the Responses API."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4.1")
        self._timeout = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is not set.")

    @property
    def name(self) -> str:
        return f"openai/{self._model}"

    def complete(self, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        text, _ = self.complete_with_usage(system, user, max_tokens=max_tokens)
        return text

    def complete_with_usage(
        self, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> tuple[str, dict]:
        client = _client(self._api_key, self._timeout)
        response = with_retry(lambda: client.responses.create(
            model=self._model,
            instructions=system,
            input=user,
            max_output_tokens=max_tokens,
            # Sampling parameters — set explicitly to API defaults for reproducibility.
            # These values are cited in thesis Table A.1 (Experimental Configuration).
            temperature=1.0,       # default: 1.0 — not reduced, preserves natural decision variance
            top_p=1.0,             # default: 1.0 — full token distribution, no nucleus truncation
            # top_k is not a parameter in the Responses API — not applicable
            # store is not set (defaults to True) — responses stored for 30 days per OpenAI policy
            # stream is not set (defaults to False) — full response returned in one payload
            # metadata is not set — no custom key-value attribution passed to the API
        ))
        usage = getattr(response, "usage", None)
        return getattr(response, "output_text", "") or "", _usage_dict(usage)

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tool_choice: dict | None = None,
    ) -> dict:
        if not tools:
            return super().complete_with_tools(
                system, messages, tools, max_tokens=max_tokens, tool_choice=tool_choice
            )

        client = _client(self._api_key, self._timeout)
        response = with_retry(lambda: client.responses.create(
            model=self._model,
            instructions=system,
            input=_to_openai_input(messages),
            tools=[_to_openai_tool(tool) for tool in tools],
            tool_choice=_to_openai_tool_choice(tool_choice),
            max_output_tokens=max_tokens,
        ))
        return _to_provider_response(response)


def _client(api_key: str, timeout: float):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed. Run: pip install openai") from exc
    return OpenAI(api_key=api_key, timeout=timeout, max_retries=0)


def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
    }


def _to_openai_tool_choice(tool_choice: dict | None) -> str | dict | None:
    if not tool_choice:
        return None
    if tool_choice.get("type") == "any":
        return "required"
    name = tool_choice.get("name") or tool_choice.get("tool")
    return {"type": "function", "name": name} if name else tool_choice


def _to_openai_input(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
        elif role == "assistant":
            out.extend(_assistant_items(content))
        elif role == "user":
            out.extend(_tool_result_items(content))
    return out


def _assistant_items(content: Any) -> list[dict]:
    items: list[dict] = []
    for block in content if isinstance(content, list) else []:
        if block.get("type") == "text":
            items.append({"role": "assistant", "content": block.get("text", "")})
        elif block.get("type") == "tool_use":
            items.append({
                "type": "function_call",
                "call_id": block.get("id", ""),
                "name": block.get("name", ""),
                "arguments": json.dumps(block.get("input") or {}),
            })
    return items


def _tool_result_items(content: Any) -> list[dict]:
    return [
        {
            "type": "function_call_output",
            "call_id": block.get("tool_use_id", ""),
            "output": str(block.get("content") or ""),
        }
        for block in content if isinstance(content, list)
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]


def _to_provider_response(response: Any) -> dict:
    calls = [
        item for item in getattr(response, "output", [])
        if getattr(item, "type", None) == "function_call"
    ]
    usage = getattr(response, "usage", None)
    if not calls:
        return {
            "stop_reason": "end_turn",
            "content": getattr(response, "output_text", "") or "",
            "tool_use": None,
            "tool_capable": True,
            "usage": _usage_dict(usage),
        }

    tool_uses = [_tool_use(call) for call in calls]
    content = [
        {"type": "text", "text": getattr(response, "output_text", "") or ""},
        *[
            {"type": "tool_use", "id": tool["id"], "name": tool["name"], "input": tool["input"]}
            for tool in tool_uses
        ],
    ]
    return {
        "stop_reason": "tool_use",
        "content": [block for block in content if block.get("text") or block["type"] == "tool_use"],
        "tool_use": tool_uses[0] if tool_uses else None,
        "tool_uses": tool_uses,
        "tool_capable": True,
        "usage": _usage_dict(usage),
    }


def _tool_use(call: Any) -> dict:
    try:
        args = json.loads(getattr(call, "arguments", "") or "{}")
    except json.JSONDecodeError:
        args = {}
    return {
        "id": getattr(call, "call_id", None) or getattr(call, "id", ""),
        "name": getattr(call, "name", ""),
        "input": args if isinstance(args, dict) else {},
    }


def _usage_dict(usage: Any) -> dict:
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
    }
