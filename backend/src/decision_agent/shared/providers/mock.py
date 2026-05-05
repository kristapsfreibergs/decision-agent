from __future__ import annotations

import json

from decision_agent.shared.providers.base import LLMProvider


def _extract_schema(system: str) -> dict:
    start = system.find("{")
    if start == -1:
        return {}

    depth = 0
    for index, char in enumerate(system[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(system[start : index + 1])
                except json.JSONDecodeError:
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

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
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
