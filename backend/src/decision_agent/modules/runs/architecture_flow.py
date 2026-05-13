from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.proposal import propose_architecture, validate_architecture_proposal
from decision_agent.modules.runs.io import _load_run, _write_json
from decision_agent.modules.runs.state import (
    ARCHITECTURE_APPROVED,
    ARCHITECTURE_BUILD_STARTED,
    ARCHITECTURE_PROPOSAL_REJECTED,
    ARCHITECTURE_PROPOSAL_VALIDATED,
    ARCHITECTURE_PROPOSED,
    ARCHITECTURE_REJECTED,
    GOAL_STRUCTURE_CLASSIFIED,
    PACKAGES_DECOMPOSED,
    PLANNING_ARTIFACT_APPROVED,
    PLANNING_ARTIFACT_CREATED,
    PLANNING_ARTIFACT_REJECTED,
    TOPOLOGY_BUILT,
)
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.base import LLMProvider

def build_architecture_proposal(run_id: str, root: Path, provider: LLMProvider, prebuilt_artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")

    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {"event": ARCHITECTURE_BUILD_STARTED, "run_id": run_id, "provider": provider.name},
    )

    if prebuilt_artifact is not None:
        from decision_agent.modules.architectures.proposal import artifact_to_proposal
        # Patch planning_id and run_id to match the actual run
        prebuilt_artifact = {**prebuilt_artifact, "planning_id": f"planning/{run['decision_type']}/{run_id}", "run_id": run_id}
        artifact = prebuilt_artifact
        proposal = artifact_to_proposal(artifact, run)
    else:
        artifact, proposal = propose_architecture(run, provider, root)
    proposal_result = validate_architecture_proposal(proposal)
    if not proposal_result["valid"]:
        append_audit_event(
            audit_path,
            {
                "event": ARCHITECTURE_PROPOSAL_REJECTED,
                "run_id": run_id,
                "issues": proposal_result["issues"],
            },
        )
        raise ValueError(f"Invalid architecture proposal: {'; '.join(proposal_result['issues'])}")

    _write_json(run_dir / "planning-artifact.json", artifact)
    _write_json(run_dir / "architecture-proposal.json", proposal)
    append_audit_event(
        audit_path,
        {
            "event": GOAL_STRUCTURE_CLASSIFIED,
            "run_id": run_id,
            "shape": artifact["goal_structure"]["shape"],
            "modifiers": artifact["goal_structure"]["modifiers"],
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": TOPOLOGY_BUILT,
            "run_id": run_id,
            "shape": artifact["topology"]["shape"],
            "phase_count": len(artifact["topology"]["phases"]),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": PACKAGES_DECOMPOSED,
            "run_id": run_id,
            "package_count": len(artifact["packages"]),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": PLANNING_ARTIFACT_CREATED,
            "run_id": run_id,
            "planning_id": artifact["planning_id"],
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": ARCHITECTURE_PROPOSED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
            "worker_count": len(proposal.get("workers", [])),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": ARCHITECTURE_PROPOSAL_VALIDATED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
        },
    )
    run = _load_run(run_dir)
    return run


def approve_architecture(run_id: str, note: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    proposal = run.get("architecture_proposal")
    if not proposal:
        raise ValueError("No architecture proposal exists for this run.")

    result = validate_architecture_proposal(proposal)
    if not result["valid"]:
        raise ValueError(f"Invalid architecture proposal: {'; '.join(result['issues'])}")

    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {
            "event": ARCHITECTURE_APPROVED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
            "note": note,
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": PLANNING_ARTIFACT_APPROVED,
            "run_id": run_id,
            "planning_id": run["planning_artifact"]["planning_id"] if run.get("planning_artifact") else "",
            "note": note,
        },
    )
    run = _load_run(run_dir)
    return run


def reject_architecture(run_id: str, reason: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    if not run.get("architecture_proposal"):
        raise ValueError("No architecture proposal exists for this run.")

    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {"event": ARCHITECTURE_REJECTED, "run_id": run_id, "reason": reason},
    )
    append_audit_event(
        audit_path,
        {
            "event": PLANNING_ARTIFACT_REJECTED,
            "run_id": run_id,
            "planning_id": run["planning_artifact"]["planning_id"] if run.get("planning_artifact") else "",
            "reason": reason,
        },
    )
    run = _load_run(run_dir)
    return run

