from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.proposal import artifact_to_proposal, build_planning_artifact
from decision_agent.modules.architectures.goal_structure import classify_goal_structure
from decision_agent.shared.providers.base import LLMProvider


def suggest_task_setup(task: dict[str, Any], root: Path, provider: LLMProvider | None = None) -> dict[str, Any]:
    goal_structure = classify_goal_structure(task, provider=provider)
    modifiers = goal_structure.get("modifiers", [])

    # If the task needs clarification, return only the questions — no topology yet.
    if "needs_clarification" in modifiers:
        from decision_agent.modules.architectures.topology import build_topology
        topology = build_topology(goal_structure)
        return {
            "needs_clarification": True,
            "goal_structure": goal_structure,
            "modifiers": modifiers,
            "shape": goal_structure["shape"],
            "shape_reasoning": goal_structure["reasoning"],
            "human_questions": _generate_clarification_questions(task, goal_structure, topology, root, provider),
        }

    return _build_full_suggestion(task, goal_structure, root, provider)


def suggest_task_setup_with_answers(
    task: dict[str, Any],
    answers: list[str],
    root: Path,
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    """Re-run suggestion with clarification answers merged into the task description."""
    enriched_description = task.get("description") or ""
    if answers:
        enriched_description = enriched_description + ("\n\n" if enriched_description else "") + "Clarifications:\n" + "\n".join(f"- {a}" for a in answers if a.strip())
    enriched_task = {**task, "description": enriched_description}

    goal_structure = classify_goal_structure(enriched_task, provider=provider)
    return _build_full_suggestion(enriched_task, goal_structure, root, provider)


def _build_full_suggestion(task: dict[str, Any], goal_structure: dict[str, Any], root: Path, provider: LLMProvider | None) -> dict[str, Any]:
    from decision_agent.modules.decisions.router import classify_decision_type
    decision = classify_decision_type(task)
    preview_run = {
        "run_id": "preview",
        "decision_type": decision["decision_type"],
        "risk_level": "medium",
        "task": task,
    }
    artifact = build_planning_artifact(preview_run, root, provider=provider)
    proposal = artifact_to_proposal(artifact, preview_run)

    return {
        "needs_clarification": False,
        "_artifact": artifact,  # included so the client can pass it back to /architecture/build to skip re-calling the LLM
        "goal_structure": artifact["goal_structure"],
        "modifiers": artifact["goal_structure"]["modifiers"],
        "shape": artifact["topology"]["shape"],
        "shape_reasoning": artifact["goal_structure"]["reasoning"],
        "recommended_topology": {
            "shape": artifact["topology"]["shape"],
            "phases": artifact["topology"]["phases"],
            "gates": artifact["topology"]["gates"],
            "reasoning": artifact["topology"]["topology_reasoning"],
        },
        "package_outline": artifact["package_outline"],
        "worker_count_reasoning": artifact["worker_count_reasoning"],
        "human_questions": artifact["human_questions"],
        "suggested_architecture_mode": proposal["architecture_id"],
        "suggested_architecture_label": f"{artifact['topology']['shape']} workflow",
        "suggested_team": [
            {
                "worker_id": worker["worker_id"],
                "role": worker.get("work_layer", worker.get("layer", "worker")),
                "goal": worker["goal"],
                "phase_id": worker.get("phase_id"),
            }
            for worker in proposal["workers"]
        ],
    }


def _generate_clarification_questions(
    task: dict[str, Any],
    goal_structure: dict[str, Any],
    topology: dict[str, Any],
    root: Path,
    provider: LLMProvider | None,
) -> list[str]:
    """Generate specific clarification questions. Uses LLM if available, otherwise returns defaults."""
    default_questions = [
        "What is the expected output or deliverable?",
        "Who is the audience or end user for this task?",
        "Are there any constraints, deadlines, or specific requirements?",
    ]

    if provider is None:
        return default_questions

    shape = goal_structure["shape"]
    system = (
        "You are a task analyst. Given an underspecified task, generate 2-4 targeted clarification questions "
        "that would allow you to properly plan the work. Questions must be specific to what is missing from "
        "this task description. Respond with a JSON array of strings only."
    )
    user = (
        f"Task: {task.get('title', '')}\n"
        f"Description: {task.get('description', '') or 'none'}\n"
        f"Detected shape: {shape}\n"
        f"What specific questions would clarify what needs to be done?\n"
        "Return JSON array of question strings, e.g. [\"question 1\", \"question 2\"]"
    )

    import json, re
    try:
        raw = provider.complete(system, user, max_tokens=512)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw.strip())
        questions = json.loads(raw)
        if isinstance(questions, list) and questions:
            return [str(q) for q in questions if q]
    except Exception:
        pass

    return default_questions
