from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

from decision_agent.shared.providers.base import LLMProvider
from decision_agent.shared.providers.retry import with_retry


class OllamaProvider(LLMProvider):
    """Calls a local Ollama server via stdlib HTTP.

    Default endpoint: http://127.0.0.1:11434. Reads OLLAMA_HOST and OLLAMA_MODEL
    env vars as fallbacks. Tools are translated into Ollama's function-calling
    schema; responses are translated back into the internal Anthropic-shaped
    contract used by the runner. Falls back to a JSON-envelope parser when the
    model emits tool calls as plain text instead of using tool_calls.
    """

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
                        "input_tokens": 0,  # Ollama /api/chat doesn't report prompt tokens
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


def _to_ollama_tools(tools: list[dict]) -> list[dict]:
    converted = []
    for tool in tools:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema") or {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
        )
    return converted


def _to_ollama_messages(system: str, messages: list[dict]) -> list[dict]:
    """Translate the runner's Anthropic-style message list into Ollama format.

    The runner appends:
      - {"role": "assistant", "content": [<content_blocks with text/tool_use>]}
      - {"role": "user", "content": [{"type":"tool_result","tool_use_id":...,"content":...}]}

    Ollama wants:
      - {"role": "assistant", "content": "<text>", "tool_calls": [...]}
      - {"role": "tool", "content": "<result>"}
    """
    out: list[dict] = [{"role": "system", "content": system}]
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": block.get("input") or {},
                        }
                    }
                )
            elif btype == "tool_result":
                out.append(
                    {
                        "role": "tool",
                        "content": str(block.get("content") or ""),
                    }
                )
        if text_parts or tool_calls:
            msg: dict[str, Any] = {
                "role": role if role in {"assistant", "user"} else "assistant",
                "content": "\n".join(text_parts),
            }
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
    return out


def _extract_json_envelopes(text: str, allowed_names: set[str]) -> list[dict]:
    """Parse `{"tool":"<name>","input":{...}}` envelopes a small model may emit.

    Used as a fallback when the model returns tool-call intent in plain text
    instead of using the tool_calls API. Only envelopes naming an allowed tool
    are kept; other JSON is ignored. Handles nested braces via balanced scan.
    """
    if not text:
        return []
    calls: list[dict] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape_next = False
        end = -1
        for j in range(i, n):
            ch = text[j]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end == -1:
            break
        snippet = text[i:end + 1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            i += 1
            continue
        i = end + 1
        if not isinstance(data, dict):
            continue
        name = data.get("tool")
        if not isinstance(name, str) or name not in allowed_names:
            continue
        arguments = data.get("input") if isinstance(data.get("input"), dict) else {}
        calls.append({"function": {"name": name, "arguments": arguments}})
    return calls
