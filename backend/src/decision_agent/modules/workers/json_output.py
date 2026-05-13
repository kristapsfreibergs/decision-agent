from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

def _extract_json(text: str) -> dict[str, Any]:
    """Extract first JSON object from text, handling prose preamble and markdown fences."""
    # Try direct parse first (clean response)
    stripped = text.strip()
    # Strip ```json fences if present
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```\s*$", "", stripped.strip())
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    # Find the first { and try to parse a JSON object from there
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")
    # Find the matching closing brace using a stack
    depth = 0
    in_string = False
    escape_next = False
    end = -1
    for i, ch in enumerate(text[start:], start):
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
                end = i
                break
    if end == -1:
        raise ValueError("Unterminated JSON object in response")
    return json.loads(text[start:end + 1])


def _validate_output(output: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Basic schema validation: check required fields are present."""
    issues = []
    required = schema.get("required", [])
    props = schema.get("properties", {})
    for field in required:
        if field not in output:
            issues.append(f"Missing required field: {field}")
            continue
        expected_type = props.get(field, {}).get("type")
        if expected_type == "string" and not isinstance(output[field], str):
            issues.append(f"Field '{field}' must be a string.")
        elif expected_type == "array" and not isinstance(output[field], list):
            issues.append(f"Field '{field}' must be an array.")
        elif expected_type == "object" and not isinstance(output[field], dict):
            issues.append(f"Field '{field}' must be an object.")
    return issues


def _write_worker_output(
    project_root: Path,
    run_id: str,
    worker_id: str,
    output: dict[str, Any],
) -> str:
    output_dir = project_root / "data" / "runs" / run_id / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{worker_id}.json"
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path.relative_to(project_root).as_posix()
