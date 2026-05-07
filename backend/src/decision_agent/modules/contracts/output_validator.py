from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.governance.dsc import (
    ScopeContract,
    check_output_against_scope,
)
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.governance.paap import evaluate_paap


def validate_contractual_output(
    output: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path | None = None,
) -> list[str]:
    """Run declared output validators against worker's final JSON.

    This runs AFTER schema validation in runner.py. Each validator listed in
    contract["validators"] maps to a domain-specific check on the output content.

    Validators are driven by contract declarations — no domain knowledge is hardcoded here.
    The evidence_profile is read from the contract so any domain's blocked sources and
    authority weights are automatically enforced.

    project_root is needed for PAAP to persist scored evidence records under
    data/runs/{run_id}/evidence/. Tests that don't care about persistence may
    omit it; the validator still reports threshold issues.
    """
    issues: list[str] = []
    evidence_profile = contract.get("evidence_profile") or {}
    cfg = LayerConfig.from_dict(contract.get("layer_config"))
    paap_record = None
    for validator in contract.get("validators", []):
        if validator == "evidence_sources_declared":
            issues.extend(_check_evidence_sources(output, evidence_profile))
            if cfg.paap_enabled:
                paap_issues, paap_record = evaluate_paap(output, contract, project_root)
                issues.extend(paap_issues)
        elif validator == "write_scope":
            issues.extend(_check_write_scope(output, contract))
        elif validator == "dsc_scope":
            issues.extend(_check_dsc_scope(output, contract))
    return issues


def _check_dsc_scope(output: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    """dsc_scope: enforce decision-scope rules embedded on the contract.

    Scope is embedded into the contract at generation time so this check stays
    pure (no run-record lookup). If no scope_contract is on the contract, the
    DSC layer was disabled or the domain is permissive — return no issues.

    required_evidence_classes is only enforced for workers that already declare
    `evidence_sources_declared`, so it doesn't fire on intake workers that
    aren't expected to cite sources.
    """
    scope_dict = contract.get("scope_contract")
    if not scope_dict:
        return []
    try:
        scope = ScopeContract.from_dict(scope_dict)
    except (KeyError, TypeError):
        return ["dsc_scope: scope_contract on contract is malformed."]
    enforce_required = "evidence_sources_declared" in (contract.get("validators") or [])
    return check_output_against_scope(
        output, scope, enforce_required_evidence=enforce_required
    )


def _check_evidence_sources(output: dict[str, Any], evidence_profile: dict[str, Any]) -> list[str]:
    """evidence_sources_declared: output must declare at least one evidence source.

    Blocked source types and zero-weight sources are read from evidence_profile so
    this check works for any domain, not just procurement.

    Blocked sources default to ["model_inference"] if the profile does not specify any.
    A source with authority_weight == 0.0 is always blocked regardless of name.
    """
    authority_weights: dict[str, float] = evidence_profile.get("authority_weights", {})
    # Build the set of blocked source type names from the evidence profile.
    # A source is blocked if its declared authority_weight is 0.0.
    # Fall back to blocking "model_inference" if no profile is provided.
    blocked: set[str] = {
        name for name, weight in authority_weights.items() if float(weight) == 0.0
    } or {"model_inference"}

    sources = output.get("evidence_sources", [])
    if not sources:
        return ["evidence_sources_declared: no evidence_sources declared in output."]

    issues = []
    for source in sources:
        if isinstance(source, str):
            label = source.lower()
            if any(b in label for b in blocked):
                issues.append(
                    f"evidence_sources_declared: blocked source type cited: '{source}'."
                )
        elif isinstance(source, dict):
            src_type = str(source.get("type", "")).lower()
            if any(b in src_type for b in blocked):
                issues.append(
                    f"evidence_sources_declared: blocked source type cited: '{src_type}'."
                )
            weight = source.get("authority_weight")
            if weight is not None and float(weight) == 0.0:
                issues.append(
                    f"evidence_sources_declared: source '{src_type}' has authority_weight=0 — not allowed."
                )
    return issues


def _check_write_scope(output: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    """write_scope: every file listed in files_changed must fall within contract write_paths."""
    write_paths = contract.get("write_paths", [])
    issues = []
    for changed_file in output.get("files_changed", []):
        allowed = any(
            changed_file.startswith(wp.rstrip("*").rstrip("/"))
            for wp in write_paths
        )
        if not allowed:
            issues.append(
                f"write_scope: '{changed_file}' is not within write_paths {write_paths}"
            )
    return issues
