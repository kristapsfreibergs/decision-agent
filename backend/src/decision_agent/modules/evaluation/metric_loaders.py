from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision_agent.modules.governance.dsc import ScopeContract

BASELINE_LIFECYCLE_EVENTS = (
    "run_created",
    "run_started",
    "contract_created",
    "worker_started",
    "worker_submitted",
    "validation_passed",
    "gate_approved",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _list_outputs(run_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    outputs_dir = run_dir / "outputs"
    if not outputs_dir.exists():
        return []
    items: list[tuple[str, dict[str, Any]]] = []
    for output_file in sorted(outputs_dir.glob("*.json")):
        data = _read_json(output_file)
        if isinstance(data, dict):
            items.append((output_file.stem, data))
    return items


def _load_audit(run_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(run_dir / "audit.jsonl")


def _load_run_record(run_dir: Path) -> dict[str, Any]:
    return _read_json(run_dir / "run-record.json") or {}


def _load_proposal(run_dir: Path) -> dict[str, Any] | None:
    return _read_json(run_dir / "architecture-proposal.json")


def _load_scope(run_dir: Path) -> ScopeContract | None:
    data = _read_json(run_dir / "scope.json")
    if data:
        return ScopeContract.from_dict(data)
    record = _load_run_record(run_dir)
    if record.get("decision_type") == "procurement":
        from decision_agent.modules.architectures.domains.procurement import (
            DOMAIN_ID,
            SCOPE_PROFILE,
        )
        return ScopeContract(
            run_id=record.get("run_id", ""),
            domain=DOMAIN_ID,
            allowed_evidence_classes=tuple(SCOPE_PROFILE["allowed_evidence_classes"]),
            required_evidence_classes=tuple(SCOPE_PROFILE["required_evidence_classes"]),
            out_of_scope_markers=tuple(SCOPE_PROFILE["out_of_scope_markers"]),
            scope_phrase_blocklist=tuple(SCOPE_PROFILE["scope_phrase_blocklist"]),
        )
    return None


def _load_evidence_profile(run_dir: Path) -> dict[str, Any]:
    record = _load_run_record(run_dir)
    if record.get("decision_type") == "procurement":
        from decision_agent.modules.architectures.domains.procurement import EVIDENCE_PROFILE
        return EVIDENCE_PROFILE
    proposal = _load_proposal(run_dir)
    if proposal:
        return proposal.get("evidence_profile") or {}
    return {}
