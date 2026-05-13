from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from decision_agent.modules.runs.state import VALIDATION_FAILED, WORKER_MESSAGE
from decision_agent.modules.workers.checkpoints import _load_checkpoint, _save_checkpoint
from decision_agent.modules.workers.context import _read_context_files
from decision_agent.modules.workers.prompts import _build_system_prompt, _build_user_prompt
from decision_agent.modules.workers.tools import TOOL_DEFINITIONS, execute_tool
from decision_agent.shared.providers.base import LLMProvider


def _minimum_tool_requirement_met(called_tools: list[str], allowed_tools: list[str]) -> bool:
    if not any(tool in allowed_tools for tool in ("read_file", "write_file", "list_files", "run_tests")):
        return True
    return bool(called_tools)


def _json_nudge(count: int) -> str:
    if count == 1:
        return (
            "You have gathered all the information. Now produce the final JSON. "
            "If write_file is in your allowed tools and you haven't written the artifact yet, "
            "call write_file now. Then output ONLY the final JSON object. "
            "Start your response with { and end with }. No preamble."
        )
    return (
        "OUTPUT THE JSON NOW. "
        "Do not call any more tools. Do not explain. "
        "Your entire response must be a single valid JSON object starting with { and ending with }. "
        "Match the schema exactly. Output nothing else."
    )


def _run_model_loop(
    run_id: str,
    worker_id: str,
    contract: dict[str, Any],
    project_root: Path,
    provider: LLMProvider,
    is_retry: bool,
    emit: Callable[..., None],
) -> tuple[str, int, int, float]:
    context_files = _read_context_files(contract, project_root)
    system = _build_system_prompt(contract)
    user = _build_user_prompt(contract, context_files)
    allowed_tools = contract.get("allowed_tools", [])
    active_tool_defs = [tool for tool in TOOL_DEFINITIONS if tool["name"] in allowed_tools]
    checkpoint = _load_checkpoint(project_root, run_id, worker_id) if is_retry else None
    if checkpoint:
        messages: list[dict[str, Any]] = checkpoint["messages"]
        called_tools: list[str] = checkpoint["called_tools"]
        start_step: int = checkpoint["step"]
    else:
        messages = [{"role": "user", "content": user}]
        called_tools = []
        start_step = 0
    max_steps = contract.get("max_steps", 6)
    raw_response = ""
    json_nudge_count = 0
    total_input_tokens = 0
    total_output_tokens = 0
    worker_wall_start = time.monotonic()
    for step in range(start_step, max_steps):
        first_turn = len(called_tools) == 0 and len(messages) == 1
        force_tool = first_turn and bool(active_tool_defs) and not _minimum_tool_requirement_met(called_tools, allowed_tools)
        response = provider.complete_with_tools(
            system,
            messages,
            active_tool_defs,
            tool_choice={"type": "any"} if force_tool else None,
        )
        usage = response.get("usage") or {}
        total_input_tokens += int(usage.get("input_tokens", 0))
        total_output_tokens += int(usage.get("output_tokens", 0))
        if response["stop_reason"] == "tool_use":
            tool_uses = response.get("tool_uses") or ([response.get("tool_use")] if response.get("tool_use") else [])
            if not tool_uses:
                emit(VALIDATION_FAILED, reason="Provider returned tool_use without a tool payload.")
                raise ValueError(f"Worker {worker_id} returned an invalid tool_use response.")
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
                tool_results.append({"type": "tool_result", "tool_use_id": tool["id"], "content": result})
            messages.append({"role": "assistant", "content": response["content"]})
            messages.append({"role": "user", "content": tool_results})
            _save_checkpoint(project_root, run_id, worker_id, step + 1, messages, called_tools)
            continue
        if json_nudge_count == 0 and response.get("tool_capable") is not False and not _minimum_tool_requirement_met(called_tools, allowed_tools):
            emit(VALIDATION_FAILED, reason="Provider returned final text before required tool use.")
            raise ValueError(f"Worker {worker_id} returned final text before required tool use.")
        raw_response = str(response["content"])
        emit(WORKER_MESSAGE, role="agent", text=raw_response[:500])
        if "{" not in raw_response and step < max_steps - 1:
            json_nudge_count += 1
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({"role": "user", "content": _json_nudge(json_nudge_count)})
            continue
        break
    if not raw_response:
        emit(VALIDATION_FAILED, reason=f"Worker exceeded max_steps={max_steps} before final JSON.")
        raise ValueError(f"Worker {worker_id} exceeded max_steps before returning final JSON.")
    return raw_response, total_input_tokens, total_output_tokens, worker_wall_start
