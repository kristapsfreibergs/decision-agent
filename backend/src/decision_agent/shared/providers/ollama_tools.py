from __future__ import annotations

import json
from typing import Any

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
