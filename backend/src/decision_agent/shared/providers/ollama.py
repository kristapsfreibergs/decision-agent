from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

from decision_agent.shared.providers.base import LLMProvider
from decision_agent.shared.providers.retry import with_retry
from decision_agent.shared.providers.ollama_tools import _extract_json_envelopes, _to_ollama_messages, _to_ollama_tools


class OllamaProvider(LLMProvider):
    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self._model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
        host_value = host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        if not host_value.startswith("http"):
            host_value = f"http://{host_value}"
        self._host = host_value.rstrip("/")
        self._timeout_seconds = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))

    @property
    def name(self) -> str:
        return f"ollama/{self._model}"

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._host}{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        def _do_request() -> dict[str, Any]:
            try:
                with urllib.request.urlopen(request, timeout=self._timeout_seconds) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"OllamaProvider could not reach {url}: {exc}. "
                    "Is `ollama serve` running?"
                ) from exc

        return with_retry(_do_request)

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "options": {"temperature": 0, "num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = self._post("/api/chat", payload)
        return ((data.get("message") or {}).get("content")) or ""

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 4096,
        tool_choice: dict | None = None,
    ) -> dict:
        if not tools:
            return super().complete_with_tools(
                system, messages, tools, max_tokens=max_tokens, tool_choice=tool_choice
            )

        ollama_messages = _to_ollama_messages(system, messages)
        ollama_tools = _to_ollama_tools(tools)
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "options": {"temperature": 0, "num_predict": max_tokens},
            "messages": ollama_messages,
            "tools": ollama_tools,
        }
        data = self._post("/api/chat", payload)
        message = data.get("message") or {}
        text = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []

        if not tool_calls and text:
            envelope_calls = _extract_json_envelopes(text, {t["name"] for t in tools})
            if envelope_calls:
                tool_calls = envelope_calls
                text = ""

        if tool_calls:
            tool_uses = []
            content_blocks: list[dict] = []
            if text:
                content_blocks.append({"type": "text", "text": text})
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or call.get("name")
                arguments = fn.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                if not name:
                    continue
                tool_id = call.get("id") or f"toolcall_{uuid4().hex[:12]}"
                tool_uses.append({"id": tool_id, "name": name, "input": arguments})
                content_blocks.append(
                    {"type": "tool_use", "id": tool_id, "name": name, "input": arguments}
                )
            if tool_uses:
                return {
                    "stop_reason": "tool_use",
                    "content": content_blocks,
                    "tool_use": tool_uses[0],
                    "tool_uses": tool_uses,
                    "tool_capable": True,
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": data.get("eval_count", 0),
                    },
                }

        return {
            "stop_reason": "end_turn",
            "content": text,
            "tool_use": None,
            "tool_capable": True,
            "usage": {
                "input_tokens": 0,
                "output_tokens": data.get("eval_count", 0),
            },
        }

