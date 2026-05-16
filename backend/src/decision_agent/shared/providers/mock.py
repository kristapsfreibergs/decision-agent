from __future__ import annotations

import json

from decision_agent.shared.providers.base import DEFAULT_MAX_TOKENS, LLMProvider


_SCHEMA_ANCHOR = "Schema you must match:"


def _extract_schema(system: str) -> dict:
    """Find the JSON schema embedded after the 'Schema you must match:' anchor.

    Falls back to the first balanced JSON object if the anchor is absent.
    """
    anchor_pos = system.find(_SCHEMA_ANCHOR)
    search_start = anchor_pos + len(_SCHEMA_ANCHOR) if anchor_pos != -1 else 0
    cursor = search_start
    while cursor < len(system):
        start = system.find("{", cursor)
        if start == -1:
            return {}
        depth = 0
        for index, char in enumerate(system[start:], start=start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    snippet = system[start : index + 1]
                    try:
                        return json.loads(snippet)
                    except json.JSONDecodeError:
                        cursor = index + 1
                        break
        else:
            return {}
    return {}


def _mock_value(field: str, schema: dict) -> object:
    field_type = schema.get("type")
    if field_type == "array":
        if field == "files_changed":
            return []
        return [f"Mock {field.replace('_', ' ')} item."]
    if field_type == "object":
        return {"mock": True}
    return f"Mock {field.replace('_', ' ')}."


class MockProvider(LLMProvider):
    """Returns deterministic JSON output for testing without an API key."""

    @property
    def name(self) -> str:
        return "mock"

    def complete(self, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        schema = _extract_schema(system)
        required = schema.get("required", ["summary", "files_changed"])
        properties = schema.get("properties", {})
        output = {
            field: _mock_value(field, properties.get(field, {}))
            for field in required
        }
        if "summary" in output:
            output["summary"] = "Mock worker completed task (no real model call)."
        if "files_changed" in output:
            output["files_changed"] = []
        return json.dumps(output, indent=2)
