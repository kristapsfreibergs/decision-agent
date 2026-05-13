from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.modules.architectures.registry import find_architecture_for_decision
from decision_agent.modules.contracts.validator import validate_architecture, validate_worker_contract
from decision_agent.modules.decisions.router import classify_decision_type
from decision_agent.modules.governance.dsc import derive_scope_contract, persist_scope_contract
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.runs.io import _run_id, _scope_profile_for_decision, _write_json
from decision_agent.modules.runs.state import SCOPE_BOUND, enrich_run
from decision_agent.shared.audit_log import append_audit_event, read_audit

def instantiate_worker_contract(
    architecture: dict[str, Any],
    worker: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "worker_id": worker["worker_id"],
        "layer": worker["layer"],
        "work_layer": worker.get("work_layer", worker["layer"]),
        "architecture_id": architecture["id"],
        "run_id": run_id,
        "decision_id": task.get("task_id") or uuid4().hex,
        "decision_type": architecture["decision_type"],
        "risk_level": architecture["risk_level"],
        "goal": worker["goal"],
        "context": {
            "task_title": task.get("title"),
            "task_summary": task.get("description"),
            "router_reason": decision["reason"],
        },
        "read_paths": deepcopy(worker["read_paths"]),
        "write_paths": deepcopy(worker["write_paths"]),
        "allowed_tools": deepcopy(worker["allowed_tools"]),
        "max_steps": worker["max_steps"],
        "output_schema": deepcopy(worker["output_schema"]),
        "validators": deepcopy(worker["validators"]),
        "completion_contract": worker["completion_contract"],
    }


def create_run(
    task: dict[str, Any],
    root: Path,
    layer_config: LayerConfig | dict[str, Any] | None = None,
    provider_override: str | None = None,
    benchmark_mode: bool = False,
) -> dict[str, Any]:
    decision = classify_decision_type(task)
    architecture = find_architecture_for_decision(decision["decision_type"])

    if isinstance(layer_config, dict):
        cfg = LayerConfig.from_dict(layer_config)
    elif isinstance(layer_config, LayerConfig):
        cfg = layer_config
    else:
        cfg = LayerConfig.full()

    run_id = _run_id()
    run_dir = root / "data" / "runs" / run_id
    contracts_dir = run_dir / "contracts"
    audit_path = run_dir / "audit.jsonl"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "task.json", task)

    # Dynamic runs (no registered static architecture) skip bootstrap contracts.
    # Architecture and contracts are built later via /architecture/build and /architecture/generate-contracts.
    is_dynamic = architecture is None

    if not is_dynamic:
        architecture_validation = validate_architecture(architecture)
        if not architecture_validation["valid"]:
            joined = "; ".join(architecture_validation["issues"])
            raise ValueError(f"Invalid architecture {architecture['id']}: {joined}")

    append_audit_event(
        audit_path,
        {
            "event": "run_created",
            "run_id": run_id,
            "decision_type": decision["decision_type"],
            "architecture_id": architecture["id"] if architecture else "dynamic",
            "task_title": task.get("title"),
            "layer_config": cfg.to_dict(),
            "provider_override": provider_override,
            "benchmark_mode": bool(benchmark_mode),
        },
    )

    # DSC: derive and persist scope contract for known domains when enabled.
    scope_profile, domain = _scope_profile_for_decision(decision["decision_type"])
    scope_contract_dict: dict[str, Any] | None = None
    if cfg.dsc_enabled and scope_profile:
        scope = derive_scope_contract(run_id, domain, scope_profile)
        persist_scope_contract(scope, root / "data" / "runs")
        scope_contract_dict = scope.to_dict()
        append_audit_event(
            audit_path,
            {
                "event": SCOPE_BOUND,
                "run_id": run_id,
                "domain": domain,
                "allowed_evidence_classes": list(scope.allowed_evidence_classes),
                "required_evidence_classes": list(scope.required_evidence_classes),
            },
        )

    contracts: list[dict[str, Any]] = []
    if not is_dynamic:
        contracts = [
            instantiate_worker_contract(architecture, worker, task, run_id, decision)
            for worker in architecture["workers"]
        ]
        for contract in contracts:
            if scope_contract_dict:
                contract["scope_contract"] = deepcopy(scope_contract_dict)
                if cfg.dsc_enabled and "dsc_scope" not in contract.get("validators", []):
                    contract.setdefault("validators", []).append("dsc_scope")
            contract["layer_config"] = cfg.to_dict()
            result = validate_worker_contract(contract)
            if not result["valid"]:
                joined = "; ".join(result["issues"])
                raise ValueError(f"Invalid contract {contract['worker_id']}: {joined}")
            _write_json(contracts_dir / f"{contract['worker_id']}.json", contract)
            append_audit_event(
                audit_path,
                {
                    "event": "contract_created",
                    "run_id": run_id,
                    "worker_id": contract["worker_id"],
                    "layer": contract["layer"],
                    "goal": contract["goal"],
                    "write_paths": contract["write_paths"],
                },
            )

    run_record = {
        "run_id": run_id,
        "decision_id": task.get("task_id"),
        "decision_type": decision["decision_type"],
        "router_confidence": decision["confidence"],
        "router_reason": decision["reason"],
        "architecture_id": architecture["id"] if architecture else "dynamic",
        "risk_level": architecture["risk_level"] if architecture else "medium",
        "action_gate": deepcopy(architecture["action_gate"]) if architecture else {"type": "human_gate", "requires_human_review": True, "automatic_final_action": False},
        "outcome_metrics": deepcopy(architecture["outcome_metrics"]) if architecture else ["planning_artifact_created", "architecture_approved", "contracts_generated"],
        "layer_config": cfg.to_dict(),
        "provider_override": provider_override,
        "benchmark_mode": bool(benchmark_mode),
        "contracts": [
            {
                "worker_id": contract["worker_id"],
                "contract_file": f"contracts/{contract['worker_id']}.json",
                "write_paths": contract["write_paths"],
                "max_steps": contract["max_steps"],
            }
            for contract in contracts
        ],
    }

    _write_json(run_dir / "run-record.json", run_record)
    append_audit_event(
        audit_path,
        {"event": "run_ready", "run_id": run_id, "contract_count": len(contracts)},
    )

    audit = read_audit(audit_path)
    return enrich_run({**run_record, "run_dir": str(run_dir), "contracts": contracts, "task": task, "audit": audit})
