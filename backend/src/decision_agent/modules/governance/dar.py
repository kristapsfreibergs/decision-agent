from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.governance.paap import evidence_floor_met

DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_ESCALATE = "ESCALATE"

CONSEQUENCE_INTERNAL = "INTERNAL_REVERSIBLE"
CONSEQUENCE_EXTERNAL = "EXTERNAL_VISIBLE"
CONSEQUENCE_IRREVERSIBLE = "IRREVERSIBLE"


@dataclass(frozen=True)
class ActionProposal:
    run_id: str
    worker_id: str
    action_type: str
    target: str
    claimed_evidence_ids: tuple[str, ...]
    proposed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "action_type": self.action_type,
            "target": self.target,
            "claimed_evidence_ids": list(self.claimed_evidence_ids),
            "proposed_at": self.proposed_at,
        }


@dataclass(frozen=True)
class AuthorizationReceipt:
    receipt_id: str
    proposal: ActionProposal
    consequence_class: str
    decision: str
    rule_fired: str
    evidence_floor_met: bool
    evidence_score: float
    decided_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "proposal": self.proposal.to_dict(),
            "consequence_class": self.consequence_class,
            "decision": self.decision,
            "rule_fired": self.rule_fired,
            "evidence_floor_met": self.evidence_floor_met,
            "evidence_score": self.evidence_score,
            "decided_at": self.decided_at,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decide(
    consequence_class: str,
    floor_met: bool,
    cfg: LayerConfig,
) -> tuple[str, str]:
    """Pure deterministic decision matrix. Same inputs → same decision.

    Matrix:
      IRREVERSIBLE         + human_gate ON   → ESCALATE
      IRREVERSIBLE         + human_gate OFF  → DENY
      EXTERNAL_VISIBLE     + floor=False     → DENY
      EXTERNAL_VISIBLE     + floor=True      → ESCALATE
      INTERNAL_REVERSIBLE  + floor=True      → ALLOW
      INTERNAL_REVERSIBLE  + floor=False     → DENY
      unknown                                → DENY
    """
    if consequence_class == CONSEQUENCE_IRREVERSIBLE:
        if cfg.human_gate_enabled:
            return DECISION_ESCALATE, "irreversible_requires_human_gate"
        return DECISION_DENY, "irreversible_without_human_gate"
    if consequence_class == CONSEQUENCE_EXTERNAL:
        if not floor_met:
            return DECISION_DENY, "external_visible_evidence_floor_unmet"
        return DECISION_ESCALATE, "external_visible_requires_human_gate"
    if consequence_class == CONSEQUENCE_INTERNAL:
        if not floor_met:
            return DECISION_DENY, "internal_evidence_floor_unmet"
        return DECISION_ALLOW, "internal_with_sufficient_evidence"
    return DECISION_DENY, "unknown_consequence_class"


def build_proposal_from_output(
    output: dict[str, Any],
    contract: dict[str, Any],
) -> ActionProposal | None:
    """Build an ActionProposal if the contract declares dar_action_type."""
    action_type = contract.get("dar_action_type")
    if not action_type:
        return None
    sources = output.get("evidence_sources") or []
    cited_ids: list[str] = []
    for i, source in enumerate(sources):
        if isinstance(source, dict):
            sid = source.get("id") or f"src_{i}"
        elif isinstance(source, str):
            sid = source
        else:
            continue
        cited_ids.append(str(sid))
    target = (
        output.get("recommended_vendor")
        or output.get("target")
        or contract.get("worker_id", "unknown")
    )
    return ActionProposal(
        run_id=contract.get("run_id", "unknown"),
        worker_id=contract.get("worker_id", "unknown"),
        action_type=action_type,
        target=str(target)[:200],
        claimed_evidence_ids=tuple(cited_ids),
        proposed_at=_now_iso(),
    )


def evaluate_action(
    proposal: ActionProposal,
    contract: dict[str, Any],
    project_root: Path,
) -> AuthorizationReceipt:
    """Evaluate an action proposal against scope, evidence, and policy.

    Pure-Python decision: no LLM in the path. Same inputs → same receipt.
    """
    consequence_class = contract.get("dar_consequence_class") or CONSEQUENCE_INTERNAL
    cfg = LayerConfig.from_dict(contract.get("layer_config"))
    profile = contract.get("evidence_profile") or {}
    floor_met, mean_score = evidence_floor_met(
        proposal.run_id,
        project_root / "data" / "runs",
        profile,
    )
    decision, rule = _decide(consequence_class, floor_met, cfg)
    return AuthorizationReceipt(
        receipt_id=f"receipt_{uuid4().hex[:12]}",
        proposal=proposal,
        consequence_class=consequence_class,
        decision=decision,
        rule_fired=rule,
        evidence_floor_met=floor_met,
        evidence_score=round(mean_score, 4),
        decided_at=_now_iso(),
    )


def persist_receipt(
    receipt: AuthorizationReceipt,
    run_id: str,
    runs_dir: Path,
) -> Path:
    target = runs_dir / run_id / "authorization" / f"{receipt.receipt_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(receipt.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
