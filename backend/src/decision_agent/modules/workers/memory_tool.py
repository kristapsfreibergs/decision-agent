from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

AuditEmit = Callable[..., None]

def _execute_memory_search(
    params: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path,
    audit_emit: AuditEmit,
) -> str:
    query = str(params.get("query", "")).strip()
    limit = min(int(params.get("limit") or 10), 20)
    if not query:
        return "ERROR: memory_search requires a non-empty query."

    scope_dict = contract.get("scope_contract") or {}

    try:
        from decision_agent.shared.memory.registry import get_memory_provider
    except ImportError:
        return "ERROR: memory provider not available."

    provider = get_memory_provider(project_root / "data")
    hits = provider.search(query, scope_dict, limit=limit)
    audit_emit("tool_called", tool="memory_search", query=query, hits=len(hits))

    if not hits:
        return (
            f"No past evidence found for query '{query}' within scope. "
            "This may be the first run for this domain."
        )

    results = [
        {
            "id": h.memory_id,
            "type": h.evidence_class,
            "excerpt": h.excerpt,
            "created_at": h.created_at,
            "authority_score": h.authority_score,
            "relevance_score": h.relevance_score,
            "source_run": h.source_run_id,
            "source_worker": h.worker_id,
        }
        for h in hits
    ]
    return json.dumps(results, indent=2, ensure_ascii=False)
