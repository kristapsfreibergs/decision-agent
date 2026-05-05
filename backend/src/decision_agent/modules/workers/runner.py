from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from decision_agent.modules.runs.state import (
    VALIDATION_FAILED,
    VALIDATION_PASSED,
    WORKER_MESSAGE,
    WORKER_NEEDS_HUMAN,
    WORKER_STARTED,
    WORKER_SUBMITTED,
)
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.base import LLMProvider

MAX_CONTEXT_FILES = 12
MAX_CONTEXT_CHARS_PER_FILE = 4_000
SKIP_PATH_PARTS = {"__pycache__", ".git", "node_modules", ".venv"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".docx"}


def _build_system_prompt(contract: dict[str, Any]) -> str:
    output_schema = json.dumps(contract.get("output_schema", {}), indent=2)
    validators = ", ".join(contract.get("validators", []))
    return f"""You are a bounded worker agent operating under a strict contract.

Worker ID: {contract["worker_id"]}
Layer: {contract.get("work_layer", contract.get("layer", ""))}
Goal: {contract["goal"]}

Constraints:
- You may only read from: {", ".join(contract.get("read_paths", []))}
- You may only write to: {", ".join(contract.get("write_paths", []))}
- Allowed tools: {", ".join(contract.get("allowed_tools", []))}
- Validators that will check your output: {validators}
- Max steps: {contract.get("max_steps", 5)}
- Completion contract: {contract.get("completion_contract", "")}

IMPORTANT: Your response MUST be valid JSON matching this schema exactly:
{output_schema}

Do not include any text outside the JSON object. Do not add markdown fences."""


def _build_user_prompt(contract: dict[str, Any], context_files: dict[str, str]) -> str:
    task_ctx = contract.get("context", {})
    lines = [
        f"Task: {task_ctx.get('task_title', 'Unnamed task')}",
        f"Description: {task_ctx.get('task_summary', '')}",
        f"Router reason: {task_ctx.get('router_reason', '')}",
        "",
        "Perform your work now and return the JSON result.",
    ]
    if context_files:
        lines.append("\nAvailable context files:")
        for path, content in context_files.items():
            lines.append(f"\n--- {path} ---\n{content[:MAX_CONTEXT_CHARS_PER_FILE]}")
    return "\n".join(lines)


def _safe_relative(path: Path, root: Path) -> str | None:
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved.relative_to(root.resolve()).as_posix()


def _is_context_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    if any(part in SKIP_PATH_PARTS for part in path.parts):
        return False
    return True


def _read_context_files(contract: dict[str, Any], project_root: Path) -> dict[str, str]:
    """Read declared context paths that exist, including bounded glob expansion."""
    context: dict[str, str] = {}
    root = project_root.resolve()

    for pattern in contract.get("read_paths", []):
        if len(context) >= MAX_CONTEXT_FILES:
            break

        matches = sorted(root.glob(pattern)) if "*" in pattern else [root / pattern]
        for path in matches:
            if len(context) >= MAX_CONTEXT_FILES:
                break
            relative = _safe_relative(path, root)
            if relative is None or not _is_context_file(path):
                continue
            try:
                context[relative] = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )[:MAX_CONTEXT_CHARS_PER_FILE]
            except OSError:
                continue
    return context


def _extract_json(text: str) -> dict[str, Any]:
    """Extract first JSON object from text, stripping any markdown fences."""
    # strip ```json fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


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


def run_worker(
    run_id: str,
    worker_id: str,
    contract: dict[str, Any],
    audit_path: Path,
    project_root: Path,
    provider: LLMProvider,
) -> dict[str, Any]:
    """
    Execute one worker loop:
    1. Emit worker_started
    2. Build prompt from contract + context files
    3. Call provider
    4. Emit worker_message with raw response
    5. Parse + validate JSON
    6. Emit validation_passed / validation_failed
    7. Emit worker_submitted with result
    Returns the validated output dict.
    """
    def emit(event: str, **extra: Any) -> None:
        append_audit_event(audit_path, {"event": event, "run_id": run_id, "worker_id": worker_id, **extra})

    emit(WORKER_STARTED, provider=provider.name)

    context_files = _read_context_files(contract, project_root)
    system = _build_system_prompt(contract)
    user = _build_user_prompt(contract, context_files)

    raw_response = provider.complete(system, user)

    emit(WORKER_MESSAGE, role="agent", text=raw_response[:500])  # truncate for audit

    # Parse
    try:
        output = _extract_json(raw_response)
    except (json.JSONDecodeError, ValueError) as exc:
        emit(VALIDATION_FAILED, reason=f"JSON parse error: {exc}", raw=raw_response[:200])
        raise ValueError(f"Worker {worker_id} returned invalid JSON: {exc}") from exc

    # Validate schema
    schema = contract.get("output_schema", {})
    issues = _validate_output(output, schema)
    if issues:
        emit(VALIDATION_FAILED, reason="; ".join(issues))
        raise ValueError(f"Worker {worker_id} output failed schema validation: {'; '.join(issues)}")

    output_file = _write_worker_output(project_root, run_id, worker_id, output)
    emit(VALIDATION_PASSED)
    emit(
        WORKER_SUBMITTED,
        summary=output.get("summary", ""),
        files_changed=output.get("files_changed", []),
        output_file=output_file,
    )

    return output
