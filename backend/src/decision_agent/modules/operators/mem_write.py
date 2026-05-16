from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.shared.memory.base import MemoryItem


class MemoryWriteOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("mem_write", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        if context.memory is None:
            return OperatorResult(success=True, data={"mem_write_skipped": True})

        evidence_items = config.get("evidence_items", [])
        if not evidence_items:
            return OperatorResult(success=True, data={"mem_write_skipped": True, "reason": "no items"})

        domain = getattr(state, "domain", "unknown")
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        written_ids: list[str] = []

        for item_data in evidence_items:
            item = MemoryItem(
                source_run_id=context.run_id,
                worker_id=context.agent_id,
                evidence_class=item_data.get("evidence_class", "unknown"),
                content=item_data.get("content", ""),
                created_at=item_data.get("created_at", now),
                domain=domain,
                authority_score=item_data.get("authority_score", 0.0),
                extra=item_data.get("extra"),
            )
            memory_id = context.memory.write(item)
            written_ids.append(memory_id)

        return OperatorResult(
            success=True,
            data={"written_count": len(written_ids)},
            state_patch={"persisted_evidence_ids": written_ids},
            audit_entries=[{"event": "evidence_persisted", "count": len(written_ids)}],
        )
