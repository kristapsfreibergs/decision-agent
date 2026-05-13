from __future__ import annotations

import json
import re
from typing import Any

from decision_agent.modules.architectures.domains import procurement as _procurement_domain
from decision_agent.modules.architectures.domains import story as _story_domain
from decision_agent.shared.providers.base import LLMProvider

_DOMAIN_CATALOG: dict[str, tuple[dict, Any, tuple[str, ...]]] = {
    _story_domain.DOMAIN_ID: (
        _story_domain.DOMAIN_SPEC,
        _story_domain.build_story_decomposition,
        _story_domain.DETECTION_KEYWORDS,
    ),
    _procurement_domain.DOMAIN_ID: (
        _procurement_domain.DOMAIN_SPEC,
        _procurement_domain.build_procurement_decomposition,
        _procurement_domain.DETECTION_KEYWORDS,
    ),
}


def _build_detect_prompt() -> str:
    lines = [
        "You are a task domain classifier. Given a task title and description, "
        f"decide if it belongs to one of these known domains: {', '.join(_DOMAIN_CATALOG)}. "
    ]
    for domain_id, (spec, _, keywords) in _DOMAIN_CATALOG.items():
        lines.append(f"- {domain_id}: {', '.join(keywords[:5])}.")
    domain_list = " or ".join(
        f'{{\"domain\": \"{d}\"}}' for d in _DOMAIN_CATALOG
    )
    lines.append(f'Respond with JSON only: {domain_list} or {{"domain": null}}')
    return " ".join(lines)


def _detect_domain(task: dict[str, Any], provider: LLMProvider | None) -> str | None:
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    for domain_id, (_, _, keywords) in _DOMAIN_CATALOG.items():
        if any(w in text for w in keywords):
            return domain_id

    if provider is None:
        return None
    user = f"Task: {task.get('title', '')}\nDescription: {task.get('description', '') or 'none'}"
    try:
        raw = provider.complete(_build_detect_prompt(), user, max_tokens=64)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw.strip())
        data = json.loads(raw)
        domain = data.get("domain")
        return domain if domain in _DOMAIN_CATALOG else None
    except Exception:
        return None

PROVIDER_MARKERS = [
    "anthropic",
    "claude",
    "openai",
    "gpt",
    "gemini",
    "llama",
    "mistral",
]
