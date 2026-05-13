from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decision_agent.modules.evaluation.metric_loaders import BASELINE_LIFECYCLE_EVENTS, _list_outputs, _load_audit, _load_evidence_profile, _load_scope, _read_json
from decision_agent.modules.governance.dsc import check_output_against_scope
from decision_agent.modules.governance.paap import build_evidence_record

def scope_violations(run_dir: Path) -> int:
    scope = _load_scope(run_dir)
    if not scope:
        return 0
    total = 0
    for _, output in _list_outputs(run_dir):
        violations = check_output_against_scope(output, scope, enforce_required_evidence=False)
        total += len(violations)
    return total


def evidence_completeness(run_dir: Path) -> float:
    profile = _load_evidence_profile(run_dir)
    if not profile or "authority_weights" not in profile:
        return 0.0
    outputs = _list_outputs(run_dir)
    if not outputs:
        return 0.0
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    scores: list[float] = []
    for worker_id, output in outputs:
        if not isinstance(output.get("evidence_sources"), list):
            scores.append(0.0)
            continue
        record = build_evidence_record(output, profile, worker_id, now_utc=now)
        scores.append(record.score)
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def authorization_receipt_present(run_dir: Path) -> bool:
    auth_dir = run_dir / "authorization"
    if not auth_dir.exists():
        return False
    for receipt_file in auth_dir.glob("*.json"):
        data = _read_json(receipt_file)
        if data and data.get("decision") in {"ALLOW", "ESCALATE"}:
            return True
    return False


def unsafe_action_count(run_dir: Path) -> int:
    auth_dir = run_dir / "authorization"
    if not auth_dir.exists():
        return 0
    count = 0
    for receipt_file in auth_dir.glob("*.json"):
        data = _read_json(receipt_file)
        if data and data.get("decision") == "DENY":
            count += 1
    return count


def unsafe_approvals(run_dir: Path) -> int:
    auth_dir = run_dir / "authorization"
    if not auth_dir.exists():
        return 0
    count = 0
    for receipt_file in auth_dir.glob("*.json"):
        data = _read_json(receipt_file)
        if not data:
            continue
        if data.get("decision") in {"ALLOW", "ESCALATE"} and not data.get("evidence_floor_met", True):
            count += 1
    return count


def audit_completeness(run_dir: Path) -> float:
    audit = _load_audit(run_dir)
    seen = {event.get("event") for event in audit}
    hit = sum(1 for e in BASELINE_LIFECYCLE_EVENTS if e in seen)
    return round(hit / len(BASELINE_LIFECYCLE_EVENTS), 4)
