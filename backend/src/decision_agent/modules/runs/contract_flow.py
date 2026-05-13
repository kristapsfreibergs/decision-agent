from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.contracts.generator import generate_contracts_from_proposal
from decision_agent.modules.governance.dsc import derive_scope_contract, persist_scope_contract
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.runs.io import _has_audit_event, _load_run, _scope_profile_for_decision, _write_json
from decision_agent.modules.runs.state import (
    ARCHITECTURE_APPROVED,
    CONTRACTS_GENERATED,
    CONTRACTS_GENERATION_COMPLETED,
    CONTRACTS_GENERATION_FAILED,
    CONTRACTS_GENERATION_STARTED,
    GENERATED_CONTRACT_CREATED,
    SCOPE_BOUND,
)
from decision_agent.shared.audit_log import append_audit_event

def generate_contracts_for_approved_architecture(run_id: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    if not run.get("architecture_proposal"):
        raise ValueError("No architecture proposal exists for this run.")
    if not _has_audit_event(run, ARCHITECTURE_APPROVED):
        raise ValueError("Architecture must be approved before generating contracts.")

    proposal = run["architecture_proposal"]
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {
            "event": CONTRACTS_GENERATION_STARTED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
        },
    )

    # DSC: derive scope from the proposal's scope_profile (or domain default) and
    # persist it before contract generation so the generator can embed it.
    cfg = LayerConfig.from_dict(run.get("layer_config"))
    scope_profile = proposal.get("scope_profile")
    if not scope_profile:
        scope_profile, _ = _scope_profile_for_decision(run.get("decision_type", ""))
    domain = (proposal.get("domain_context") or {}).get("domain") or "generic"
    scope_contract_dict: dict[str, Any] | None = None
    if cfg.dsc_enabled and scope_profile:
        if not run.get("scope"):
            scope = derive_scope_contract(run_id, domain, scope_profile)
            persist_scope_contract(scope, root / "data" / "runs")
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
            scope_contract_dict = scope.to_dict()
        else:
            scope_contract_dict = run["scope"]

    contracts, issues = generate_contracts_from_proposal(proposal, run, cfg, scope_contract_dict)
    if issues:
        append_audit_event(
            audit_path,
            {
                "event": CONTRACTS_GENERATION_FAILED,
                "run_id": run_id,
                "architecture_id": proposal["architecture_id"],
                "issues": issues,
            },
        )
        raise ValueError(f"Generated contract validation failed: {'; '.join(issues)}")

    generated_dir = run_dir / "generated-contracts"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for contract in contracts:
        _write_json(generated_dir / f"{contract['worker_id']}.json", contract)
        append_audit_event(
            audit_path,
            {
                "event": GENERATED_CONTRACT_CREATED,
                "run_id": run_id,
                "worker_id": contract["worker_id"],
                "architecture_id": contract["architecture_id"],
                "write_paths": contract["write_paths"],
            },
        )

    append_audit_event(
        audit_path,
        {
            "event": CONTRACTS_GENERATION_COMPLETED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
            "contract_count": len(contracts),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": CONTRACTS_GENERATED,
            "run_id": run_id,
            "contract_count": len(contracts),
        },
    )
    planning_artifact = run.get("planning_artifact")
    if planning_artifact:
        planning_artifact["contract_summaries"] = [
            {
                "worker_id": contract["worker_id"],
                "work_package_id": contract.get("work_package_id"),
                "phase_id": contract.get("phase_id"),
                "work_layer": contract.get("work_layer"),
            }
            for contract in contracts
        ]
        _write_json(run_dir / "planning-artifact.json", planning_artifact)
    run = _load_run(run_dir)
    return run
