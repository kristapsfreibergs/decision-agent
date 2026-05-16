from __future__ import annotations

from decision_agent.modules.state.decision_state import DecisionPhase

VALID_TRANSITIONS: dict[DecisionPhase, list[DecisionPhase]] = {
    DecisionPhase.DRAFT: [DecisionPhase.EVIDENCE_INCOMPLETE],
    DecisionPhase.EVIDENCE_INCOMPLETE: [DecisionPhase.ELIGIBLE],
    DecisionPhase.ELIGIBLE: [DecisionPhase.EVALUATED],
    DecisionPhase.EVALUATED: [DecisionPhase.RECOMMENDED],
    DecisionPhase.RECOMMENDED: [DecisionPhase.APPROVED],
    DecisionPhase.APPROVED: [DecisionPhase.STATE_UPDATED],
    DecisionPhase.STATE_UPDATED: [DecisionPhase.VALIDATED],
    DecisionPhase.VALIDATED: [],
}


def validate_transition(from_phase: DecisionPhase, to_phase: DecisionPhase) -> None:
    allowed = VALID_TRANSITIONS.get(from_phase, [])
    if to_phase not in allowed:
        raise ValueError(
            f"Invalid state transition: {from_phase.value} -> {to_phase.value}. "
            f"Allowed: {[p.value for p in allowed]}"
        )
