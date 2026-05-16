from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

AuditEmit = Callable[..., None]

# Workspace file each agent writes its analysis to.
# Used to give the answering agent context when it responds.
_AGENT_WORKSPACE_FILES: dict[str, str] = {
    "requirement": "workspace/requirements.md",
    "evidence": "workspace/market_research.md",
    "eligibility": "workspace/eligibility.md",
    "evaluation": "workspace/evaluation.md",
    "comparison": "workspace/comparison.md",
    "recommendation": "workspace/recommendation_brief.md",
    "normalization": "",
    "state_update": "",
    "state_validation": "",
}


def _execute_ask_agent(
    params: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path,
    audit_emit: AuditEmit,
) -> str:
    """Handle the ask_agent tool call.

    Reads the target agent's registry entry (workspace file + output JSON),
    then does a cheap LLM call to answer the question from that context.
    Returns the answer as a plain string.
    """
    target_agent_id = str(params.get("agent_id", "")).strip()
    question = str(params.get("question", "")).strip()

    if not target_agent_id:
        return "ERROR: ask_agent requires agent_id."
    if not question:
        return "ERROR: ask_agent requires question."

    # Agent registry is passed through contract context
    registry: dict[str, Any] = contract.get("_agent_registry") or {}

    if target_agent_id not in registry:
        available = list(registry.keys())
        return (
            f"ERROR: Agent '{target_agent_id}' has not completed yet or does not exist. "
            f"Available agents: {available}"
        )

    entry = registry[target_agent_id]
    provider = entry.get("provider")
    if provider is None:
        return f"ERROR: No provider available to query agent '{target_agent_id}'."

    # Build context from the agent's workspace file and output JSON
    context_parts: list[str] = []

    workspace_rel = _AGENT_WORKSPACE_FILES.get(target_agent_id, "")
    if workspace_rel:
        run_id = contract.get("run_id") or ""
        workspace_path = project_root / "data" / "runs" / run_id / workspace_rel
        if workspace_path.exists():
            content = workspace_path.read_text(encoding="utf-8", errors="replace")[:6000]
            context_parts.append(f"=== {target_agent_id} workspace file ===\n{content}")

    output_json = entry.get("output")
    if output_json:
        import json
        context_parts.append(
            f"=== {target_agent_id} output summary ===\n"
            + json.dumps(output_json, indent=2, ensure_ascii=False)[:2000]
        )

    if not context_parts:
        return f"ERROR: Agent '{target_agent_id}' has no context to answer from."

    context_text = "\n\n".join(context_parts)
    system = (
        f"You are the {target_agent_id} agent. Another agent is asking you a question "
        f"about the analysis you completed. Answer concisely and factually from your knowledge. "
        f"Do not speculate beyond what is in your analysis."
    )
    user = f"Context from my analysis:\n\n{context_text}\n\nQuestion: {question}"

    audit_emit("tool_called", tool="ask_agent", target=target_agent_id, question=question[:100])

    try:
        answer = provider.complete(system, user, max_tokens=512)
    except Exception as exc:
        return f"ERROR: Failed to get answer from agent '{target_agent_id}': {exc}"

    return answer
