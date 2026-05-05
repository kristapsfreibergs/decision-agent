from __future__ import annotations

from typing import Any

SHAPES = {"pipeline", "search", "funnel", "debate", "checker"}

DEBATE_KEYWORDS = {"debate", "argue", "pros and cons", "counter", "position"}
SEARCH_KEYWORDS = {"research", "explore", "investigate", "discover", "compare options", "survey"}
FUNNEL_KEYWORDS = {"choose", "select", "rank", "prioritize", "screen", "shortlist"}
CHECKER_KEYWORDS = {"review", "check", "audit", "validate", "verify", "inspect", "compliance"}
HIGH_RISK_KEYWORDS = {"auth", "security", "payment", "invoice", "medical", "legal", "production", "prescription"}
AMBIGUOUS_KEYWORDS = {"something", "stuff", "improve", "fix it", "handle this"}


def classify_goal_structure(task: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(value)
        for value in [task.get("title"), task.get("description"), *(task.get("desired_outputs") or [])]
        if value
    ).lower()

    shape = "pipeline"
    reasoning = "Task appears to request producing a bounded artifact through ordered execution."

    if any(keyword in text for keyword in DEBATE_KEYWORDS):
        shape = "debate"
        reasoning = "Task language indicates adversarial comparison or position testing."
    elif any(keyword in text for keyword in SEARCH_KEYWORDS):
        shape = "search"
        reasoning = "Task language indicates exploration with convergence rather than direct assembly."
    elif any(keyword in text for keyword in FUNNEL_KEYWORDS):
        shape = "funnel"
        reasoning = "Task language indicates narrowing options toward a chosen result."
    elif any(keyword in text for keyword in CHECKER_KEYWORDS):
        shape = "checker"
        reasoning = "Task language indicates evidence collection and verification."

    modifiers: list[str] = []
    if _is_ambiguous(task, text):
        modifiers.extend(["ambiguous", "needs_clarification"])
    if any(keyword in text for keyword in HIGH_RISK_KEYWORDS):
        modifiers.extend(["high_risk", "human_gate_required"])

    return {
        "shape": shape,
        "modifiers": sorted(set(modifiers)),
        "reasoning": reasoning,
    }


def _is_ambiguous(task: dict[str, Any], text: str) -> bool:
    title = str(task.get("title") or "").strip()
    description = str(task.get("description") or "").strip()
    if len(title.split()) <= 2 and not description:
        return True
    return any(keyword in text for keyword in AMBIGUOUS_KEYWORDS)
