from __future__ import annotations

from typing import Any

BUILD_KEYWORDS = [
    "build",
    "implement",
    "scaffold",
    "repo",
    "code",
    "api",
    "backend",
    "frontend",
    "test",
    "architecture",
    "module",
]

PURCHASE_KEYWORDS = ["buy", "purchase", "groceries", "shop", "basket", "cart"]


def classify_decision_type(task: dict[str, Any]) -> dict[str, Any]:
    desired_outputs = task.get("desired_outputs")
    if not isinstance(desired_outputs, list):
        desired_outputs = []

    text = " ".join(
        str(value)
        for value in [task.get("title"), task.get("description"), *desired_outputs]
        if value
    ).lower()

    if any(keyword in text for keyword in BUILD_KEYWORDS):
        return {
            "decision_type": "software_project_build_task",
            "confidence": 0.82,
            "reason": "Task asks to build or modify software project structure.",
        }

    if any(keyword in text for keyword in PURCHASE_KEYWORDS):
        return {
            "decision_type": "personal_purchase_planning",
            "confidence": 0.68,
            "reason": "Task appears to involve purchase planning.",
        }

    return {
        "decision_type": "unknown",
        "confidence": 0.2,
        "reason": "No supported decision architecture matched the task.",
    }
