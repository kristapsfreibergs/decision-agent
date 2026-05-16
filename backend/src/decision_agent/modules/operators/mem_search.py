from __future__ import annotations

from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult


class MemorySearchOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("mem_search", is_deterministic=False)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        if context.memory is None:
            return OperatorResult(success=True, data={"mem_search_skipped": True})

        query = config.get("query", "")
        if not query:
            return OperatorResult(success=True, data={"mem_search_skipped": True, "reason": "no query"})

        scope = config.get("scope", {})
        if not scope:
            scope_profile = context.policies.get("scope_profile", {})
            scope = {
                "domain": getattr(state, "domain", ""),
                "allowed_evidence_classes": scope_profile.get("allowed_evidence_classes", []),
            }

        limit = config.get("limit", 10)
        hits = context.memory.search(query, scope, limit=limit)

        prior_evidence = [
            {
                "memory_id": hit.memory_id,
                "source_run_id": hit.source_run_id,
                "worker_id": hit.worker_id,
                "evidence_class": hit.evidence_class,
                "excerpt": hit.excerpt,
                "authority_score": hit.authority_score,
                "relevance_score": hit.relevance_score,
            }
            for hit in hits
        ]

        return OperatorResult(
            success=True,
            data={"hits_count": len(hits)},
            state_patch={"prior_evidence": prior_evidence},
            audit_entries=[{"event": "memory_searched", "hits": len(hits), "query": query[:100]}],
        )
