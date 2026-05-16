from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DecisionPhase(str, Enum):
    DRAFT = "draft"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    ELIGIBLE = "eligible"
    EVALUATED = "evaluated"
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    STATE_UPDATED = "state_updated"
    VALIDATED = "validated"


@dataclass(frozen=True)
class DecisionState:
    run_id: str
    domain: str
    phase: DecisionPhase = DecisionPhase.DRAFT
    requirements: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    normalized_data: dict[str, Any] = field(default_factory=dict)
    eligible_options: list[dict[str, Any]] = field(default_factory=list)
    scores: list[dict[str, Any]] = field(default_factory=list)
    rankings: list[dict[str, Any]] = field(default_factory=list)
    comparison: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] = field(default_factory=dict)
    evidence_sources: list[dict[str, Any]] = field(default_factory=list)
    scope_violations: list[str] = field(default_factory=list)
    authorization_receipts: list[dict[str, Any]] = field(default_factory=list)
    agent_history: list[str] = field(default_factory=list)
    prior_evidence: list[dict[str, Any]] = field(default_factory=list)
    persisted_evidence_ids: list[str] = field(default_factory=list)

    def apply_patch(self, patch: dict[str, Any]) -> DecisionState:
        changes: dict[str, Any] = {}
        for key, value in patch.items():
            if not hasattr(self, key):
                continue
            current = getattr(self, key)
            if isinstance(current, list) and isinstance(value, list):
                changes[key] = list(current) + value
            elif isinstance(current, dict) and isinstance(value, dict):
                changes[key] = {**current, **value}
            else:
                changes[key] = value
        return dataclasses.replace(self, **changes)

    def transition_to(self, phase: DecisionPhase) -> DecisionState:
        from decision_agent.modules.state.transitions import validate_transition

        validate_transition(self.phase, phase)
        return dataclasses.replace(
            self,
            phase=phase,
            agent_history=list(self.agent_history) + [phase.value],
        )

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["phase"] = self.phase.value
        return data
