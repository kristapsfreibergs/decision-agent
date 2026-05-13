from __future__ import annotations

from typing import Any

def _generic_decomposition(task: dict[str, Any], topology: dict[str, Any], goal_structure: dict[str, Any]) -> dict[str, Any]:
    task_title = task.get("title") or "Unnamed task"
    task_description = task.get("description") or ""
    task_context = f'Task: "{task_title}". {task_description}'.strip()
    human_questions = (
        ["What is the expected output or deliverable for this task?"]
        if "needs_clarification" in goal_structure.get("modifiers", [])
        else []
    )
    shape = goal_structure["shape"]
    packages = [
        {
            "id": "plain_llm",
            "worker_id": "plain_llm",
            "phase_id": "answer",
            "worker_role": "plain_llm",
            "work_layer": "answer",
            "goal": (
                f"{task_context}\n\n"
                "Handle this task as a single plain LLM worker. Do not assume access to external tools. "
                "Produce the best bounded answer from the task prompt and clearly state any assumptions or gaps."
            ),
            "read_paths": ["archive/docs/**", "archive/docs/README.md"],
            "write_paths": ["archive/docs/**"],
            "allowed_tools": [],
            "validators": ["write_scope"],
            "output_schema": {
                "type": "object",
                "required": ["summary", "answer", "assumptions", "files_changed"],
                "properties": {
                    "summary": {"type": "string"},
                    "answer": {"type": "string"},
                    "assumptions": {"type": "array"},
                    "files_changed": {"type": "array"},
                },
            },
            "completion_contract": "Return summary, answer, assumptions, files_changed.",
        }
    ]
    return {
        "domain": "generic",
        "task_subtype": "plain_llm",
        "affected_surfaces": [],
        "repo_context": {},
        "packages": packages,
        "dependencies": [],
        "human_questions": human_questions,
        "package_outline": [{"id": p["id"], "work_layer": p["work_layer"], "phase_id": p["phase_id"]} for p in packages],
        "worker_count_reasoning": {
            "total_workers": 1,
            "reason": f"No specific domain catalog matched; using one plain LLM fallback worker instead of a generated {shape} team.",
            "task_subtype": "plain_llm",
            "affected_surfaces": [],
        },
    }
