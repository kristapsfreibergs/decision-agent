from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from decision_agent.modules.runs.state import (
    VALIDATION_FAILED,
    VALIDATION_PASSED,
    WORKER_MESSAGE,
    WORKER_STARTED,
    WORKER_SUBMITTED,
)
from decision_agent.modules.contracts.output_validator import validate_contractual_output
from decision_agent.modules.workers.tools import TOOL_DEFINITIONS, execute_tool
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

MANDATORY TOOL USE:
- You MUST call your tools to do real work. Do NOT fabricate results.
- If your goal involves reading files: call read_file or list_files FIRST.
- If your goal involves writing or creating files: call write_file to actually write them.
- If write_file is available in your tools, you MUST call write_file before your final JSON.
- Do NOT claim files_changed unless you called write_file and it returned "OK:".
- Do NOT summarise what you "would" do — actually do it with tools.
- Produce the final JSON ONLY after your tool calls are complete.

OUTPUT RULES (strictly enforced):
- Your ENTIRE final response must be ONE valid JSON object.
- Start your response with {{ and end with }}.
- No preamble, no explanation, no markdown, no code fences.
- Schema you must match:
{output_schema}"""


def _build_user_prompt(contract: dict[str, Any], context_files: dict[str, str]) -> str:
    task_ctx = contract.get("context", {})
    lines = [
        f"Task: {task_ctx.get('task_title', 'Unnamed task')}",
        f"Description: {task_ctx.get('task_summary', '')}",
        f"Router reason: {task_ctx.get('router_reason', '')}",
        "",
        "Start by calling list_files or read_file to explore the codebase. Then call write_file to make changes. Only return the final JSON after your tool calls are done.",
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


def _minimum_tool_requirement_met(called_tools: list[str], allowed_tools: list[str]) -> bool:
    if "write_file" in allowed_tools:
        return "write_file" in called_tools
    if any(tool in allowed_tools for tool in ("read_file", "list_files", "run_tests")):
        return bool(called_tools)
    return True


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

    allowed_tools = contract.get("allowed_tools", [])
    active_tool_defs = [
        tool
        for tool in TOOL_DEFINITIONS
        if tool["name"] in allowed_tools
    ]

    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    max_steps = contract.get("max_steps", 6)
    raw_response = ""
    called_tools: list[str] = []

    for _ in range(max_steps):
        # Only force tool use on the very first turn (no tools called yet, no prior tool results).
        # After a tool_result message, Anthropic rejects tool_choice:"any" paired with the result.
        first_turn = len(called_tools) == 0 and len(messages) == 1
        force_tool = first_turn and bool(active_tool_defs) and not _minimum_tool_requirement_met(
            called_tools,
            allowed_tools,
        )
        response = provider.complete_with_tools(
            system,
            messages,
            active_tool_defs,
            tool_choice={"type": "any"} if force_tool else None,
        )
        if response["stop_reason"] == "tool_use":
            tool_uses = response.get("tool_uses") or ([response.get("tool_use")] if response.get("tool_use") else [])
            if not tool_uses:
                emit(VALIDATION_FAILED, reason="Provider returned tool_use without a tool payload.")
                raise ValueError(f"Worker {worker_id} returned an invalid tool_use response.")

            messages.append({"role": "assistant", "content": response["content"]})
            tool_results = []
            for tool in tool_uses:
                result = execute_tool(
                    tool["name"],
                    tool.get("input", {}),
                    contract,
                    project_root,
                    lambda event, **extra: emit(event, **extra),
                )
                called_tools.append(tool["name"])
                emit(WORKER_MESSAGE, role="tool", tool=tool["name"], result=result[:200])
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool["id"],
                        "content": result,
                    }
                )
            messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )
            continue

        if response.get("tool_capable") is not False and not _minimum_tool_requirement_met(called_tools, allowed_tools):
            emit(
                VALIDATION_FAILED,
                reason="Provider returned final text before required tool use.",
            )
            raise ValueError(f"Worker {worker_id} returned final text before required tool use.")

        raw_response = str(response["content"])
        emit(WORKER_MESSAGE, role="agent", text=raw_response[:500])  # truncate for audit
        break

    if not raw_response:
        emit(VALIDATION_FAILED, reason=f"Worker exceeded max_steps={max_steps} before final JSON.")
        raise ValueError(f"Worker {worker_id} exceeded max_steps before returning final JSON.")

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

    # Run contractual output validators (evidence_sources_declared, write_scope, etc.)
    contract_issues = validate_contractual_output(output, contract)
    if contract_issues:
        emit(VALIDATION_FAILED, reason="; ".join(contract_issues))
        raise ValueError(f"Worker {worker_id} failed contractual validation: {'; '.join(contract_issues)}")

    output_file = _write_worker_output(project_root, run_id, worker_id, output)
    emit(VALIDATION_PASSED)
    emit(
        WORKER_SUBMITTED,
        summary=output.get("summary", ""),
        files_changed=output.get("files_changed", []),
        output_file=output_file,
    )

    return output
