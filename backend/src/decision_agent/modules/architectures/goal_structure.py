from __future__ import annotations

import json
import re
from typing import Any

SHAPES = {"pipeline", "tree", "search", "funnel", "debate", "checker"}

HIGH_RISK_KEYWORDS = {"auth", "security", "payment", "invoice", "medical", "legal", "production", "prescription"}
AMBIGUOUS_KEYWORDS = {"something", "stuff", "improve", "fix it", "handle this"}

_SHAPE_DESCRIPTIONS = """
- pipeline: linear sequence of steps where each depends on the previous. Use for: writing a document, building a feature, drafting a contract, creating a report with clear sequential stages.
- tree: parallel branches that are later merged. Use for: large documents with independent chapters/sections written simultaneously, multi-part research where topics are independent, any task where sub-tasks don't depend on each other.
- search: explore a space then converge on a result. Use for: research tasks, finding the best option, investigating a topic, gathering evidence.
- funnel: collect many candidates then narrow to one. Use for: hiring, selecting a vendor, choosing a technology, screening options.
- debate: two opposing positions tested against each other. Use for: pros/cons analysis, strategic decisions with tradeoffs, policy evaluation.
- checker: verify claims or artifacts against criteria. Use for: code review, compliance audit, fact-checking, QA.
"""

_INTAKE_SOURCES = """
Available intake sources (workers that gather information before the main work begins):
- codebase_explorer: reads source files, maps project structure, summarises relevant code. Use when the task requires modifying or understanding existing code.
- web_researcher: searches the web for current information, prices, standards, news. Use when the task needs up-to-date external information.
- document_reader: reads uploaded documents, PDFs, specs, contracts. Use when the task references attached documents.
- knowledge_reader: reads from the project's persistent knowledge store. Use when past decisions or preferences are relevant.
"""

_SYSTEM = (
    "You are a task shape classifier. Given a task, select the best execution shape from this list:\n"
    + _SHAPE_DESCRIPTIONS
    + _INTAKE_SOURCES
    + "\nRespond with JSON only: "
    "{\"shape\": \"<shape>\", \"reasoning\": \"<one sentence>\", \"modifiers\": [...], \"intake_sources\": [...]}\n"
    "modifiers: add \"needs_clarification\" only if task is genuinely underspecified. "
    "intake_sources: list which intake sources this task needs (can be empty if the task needs no external information)."
)


def classify_goal_structure(task: dict[str, Any], provider: Any = None) -> dict[str, Any]:
    text = " ".join(
        str(value)
        for value in [task.get("title"), task.get("description"), *(task.get("desired_outputs") or [])]
        if value
    ).lower()

    modifiers: list[str] = []
    if _is_ambiguous(task, text):
        modifiers.extend(["ambiguous", "needs_clarification"])
    if any(keyword in text for keyword in HIGH_RISK_KEYWORDS):
        modifiers.extend(["high_risk", "human_gate_required"])

    if provider is not None:
        result = _llm_classify(task, provider)
        if result:
            # Merge modifiers — keep hard-coded high_risk/needs_clarification, add LLM suggestions
            all_modifiers = sorted(set(modifiers + result.get("modifiers", [])))
            return {
                "shape": result["shape"],
                "modifiers": all_modifiers,
                "reasoning": result["reasoning"],
                "intake_sources": result.get("intake_sources", []),
            }

    # Fallback: keyword heuristic
    return _keyword_classify(text, modifiers)


def _llm_classify(task: dict[str, Any], provider: Any) -> dict[str, Any] | None:
    user = f"Task: {task.get('title', '')}\nDescription: {task.get('description', '') or 'none'}"
    try:
        raw = provider.complete(_SYSTEM, user, max_tokens=256)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw.strip())
        data = json.loads(raw)
        shape = data.get("shape", "pipeline")
        if shape not in SHAPES:
            shape = "pipeline"
        valid_sources = {"codebase_explorer", "web_researcher", "document_reader", "knowledge_reader"}
        intake_sources = [s for s in data.get("intake_sources", []) if s in valid_sources]
        return {
            "shape": shape,
            "reasoning": data.get("reasoning", ""),
            "modifiers": [m for m in data.get("modifiers", []) if isinstance(m, str)],
            "intake_sources": intake_sources,
        }
    except Exception:
        return None


def _keyword_classify(text: str, modifiers: list[str]) -> dict[str, Any]:
    intake: list[str] = []
    if any(k in text for k in ("backend", "server", "api", "frontend", "code", "file", "class", "function", "endpoint", "module")):
        intake.append("codebase_explorer")
    if any(k in text for k in ("research", "market", "price", "news", "current", "latest", "web", "search")):
        intake.append("web_researcher")

    if any(k in text for k in ("debate", "argue", "pros and cons", "counter", "position")):
        return {"shape": "debate", "modifiers": modifiers, "reasoning": "Task language indicates adversarial comparison.", "intake_sources": intake}
    if any(k in text for k in ("research", "explore", "investigate", "discover", "survey")):
        return {"shape": "search", "modifiers": modifiers, "reasoning": "Task language indicates exploration with convergence.", "intake_sources": intake}
    if any(k in text for k in ("choose", "select", "rank", "prioritize", "screen", "shortlist")):
        return {"shape": "funnel", "modifiers": modifiers, "reasoning": "Task language indicates narrowing options.", "intake_sources": intake}
    if any(k in text for k in ("review", "check", "audit", "validate", "verify", "inspect", "compliance")):
        return {"shape": "checker", "modifiers": modifiers, "reasoning": "Task language indicates verification.", "intake_sources": intake}
    if any(k in text for k in ("chapter", "section", "part", "module", "component")):
        return {"shape": "tree", "modifiers": modifiers, "reasoning": "Task language indicates parallel independent parts.", "intake_sources": intake}
    return {"shape": "pipeline", "modifiers": modifiers, "reasoning": "Task appears to require ordered sequential execution.", "intake_sources": intake}


def _is_ambiguous(task: dict[str, Any], text: str) -> bool:
    title = str(task.get("title") or "").strip()
    description = str(task.get("description") or "").strip()
    if len(title.split()) <= 2 and not description:
        return True
    return any(keyword in text for keyword in AMBIGUOUS_KEYWORDS)
