from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.modules.runs.state import enrich_run
from decision_agent.shared.audit_log import read_audit

def _run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"run_{stamp}_{uuid4().hex[:8]}"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _read_outputs(run_dir: Path) -> dict[str, Any]:
    outputs_dir = run_dir / "outputs"
    if not outputs_dir.exists():
        return {}

    outputs: dict[str, Any] = {}
    for output_file in sorted(outputs_dir.glob("*.json")):
        output = _read_json(output_file)
        if output is not None:
            outputs[output_file.stem] = output
    return outputs


def _read_architecture_proposal(run_dir: Path) -> dict[str, Any] | None:
    return _read_json(run_dir / "architecture-proposal.json")


def _read_planning_artifact(run_dir: Path) -> dict[str, Any] | None:
    return _read_json(run_dir / "planning-artifact.json")


def _read_scope(run_dir: Path) -> dict[str, Any] | None:
    return _read_json(run_dir / "scope.json")


def _read_evidence(run_dir: Path) -> dict[str, Any]:
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.exists():
        return {}
    records: dict[str, Any] = {}
    for record_file in sorted(evidence_dir.glob("*.json")):
        record = _read_json(record_file)
        if record is not None:
            records[record_file.stem] = record
    return records


def _read_authorization(run_dir: Path) -> list[dict[str, Any]]:
    auth_dir = run_dir / "authorization"
    if not auth_dir.exists():
        return []
    receipts: list[dict[str, Any]] = []
    for receipt_file in sorted(auth_dir.glob("*.json")):
        receipt = _read_json(receipt_file)
        if receipt is not None:
            receipts.append(receipt)
    return receipts


def _scope_profile_for_decision(decision_type: str) -> tuple[dict[str, Any] | None, str]:
    """Return (scope_profile, domain) for a known decision type, or (None, 'generic')."""
    try:
        from decision_agent.modules.architectures.domains import procurement as _proc
        if decision_type == _proc.DOMAIN_ID:
            return (_proc.SCOPE_PROFILE, _proc.DOMAIN_ID)
    except Exception:
        pass
    return (None, "generic")


_RUN_PATH_RE = re.compile(r"^(data/runs/)[^/]+(/.+)$")


def _normalize_contract_run_paths(contract: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Repair stale generated contracts that still contain preview run paths."""
    normalized = deepcopy(contract)
    normalized["run_id"] = run_id
    for field in ("read_paths", "write_paths"):
        paths = normalized.get(field)
        if not isinstance(paths, list):
            continue
        normalized[field] = [
            _RUN_PATH_RE.sub(rf"\g<1>{run_id}\2", path) if isinstance(path, str) else path
            for path in paths
        ]
    return normalized


def _read_contracts_dir(contracts_dir: Path, run_id: str | None = None) -> list[dict[str, Any]]:
    contracts = []
    if contracts_dir.exists():
        for contract_file in sorted(contracts_dir.glob("*.json")):
            contract = _read_json(contract_file)
            if contract:
                if run_id is not None:
                    contract = _normalize_contract_run_paths(contract, run_id)
                contracts.append(contract)
    return contracts


def _has_audit_event(run: dict[str, Any], event_name: str) -> bool:
    return any(event.get("event") == event_name for event in run.get("audit", []))


def _load_run(run_dir: Path) -> dict[str, Any] | None:
    record = _read_json(run_dir / "run-record.json")
    if not record:
        return None
    run_id = record["run_id"]
    contracts = _read_contracts_dir(run_dir / "contracts", run_id)
    generated_contracts = _read_contracts_dir(run_dir / "generated-contracts", run_id)
    audit = read_audit(run_dir / "audit.jsonl")
    return enrich_run(
        {
            **record,
            "task": _read_json(run_dir / "task.json"),
            "contracts": contracts,
            "generated_contracts": generated_contracts,
            "audit": audit,
            "outputs": _read_outputs(run_dir),
            "architecture_proposal": _read_architecture_proposal(run_dir),
            "planning_artifact": _read_planning_artifact(run_dir),
            "scope": _read_scope(run_dir),
            "evidence": _read_evidence(run_dir),
            "authorization": _read_authorization(run_dir),
            "run_dir": str(run_dir),
        }
    )


def read_runs(root: Path) -> list[dict[str, Any]]:
    runs_dir = root / "data" / "runs"
    if not runs_dir.exists():
        return []

    runs: list[dict[str, Any]] = []
    for run_dir in sorted((entry for entry in runs_dir.iterdir() if entry.is_dir()), reverse=True):
        run = _load_run(run_dir)
        if run:
            runs.append(run)

    return runs


def read_run(run_id: str, root: Path) -> dict[str, Any] | None:
    run_dir = root / "data" / "runs" / run_id
    if not run_dir.exists():
        return None
    return _load_run(run_dir)
