from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_ARRAY_FIELDS = ["read_paths", "write_paths", "allowed_tools", "validators"]
REQUIRED_STRING_FIELDS = ["worker_id", "architecture_id", "goal", "risk_level"]


def validate_worker_contract(contract: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []

    if not isinstance(contract, dict):
        return {"valid": False, "issues": ["Contract must be a JSON object."]}

    for field in REQUIRED_STRING_FIELDS:
        if not isinstance(contract.get(field), str) or not contract[field].strip():
            issues.append(f"{field} must be a non-empty string.")

    for field in REQUIRED_ARRAY_FIELDS:
        value = contract.get(field)
        if not isinstance(value, list):
            issues.append(f"{field} must be an array.")
            continue
        if not value and field != "allowed_tools":
            issues.append(f"{field} must not be empty.")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            issues.append(f"{field} contains an invalid value.")

    if not isinstance(contract.get("max_steps"), int) or contract["max_steps"] < 1:
        issues.append("max_steps must be a positive integer.")

    if not isinstance(contract.get("output_schema"), dict):
        issues.append("output_schema must be an object.")

    if any(path in {"*", "**/*"} for path in contract.get("write_paths", [])):
        issues.append("write_paths must not grant repository-wide write access.")

    if "execute_final_action" in contract.get("allowed_tools", []):
        issues.append("workers must not be allowed to execute final actions directly.")

    return {"valid": not issues, "issues": issues}


def validate_architecture(architecture: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []

    if not isinstance(architecture, dict):
        return {"valid": False, "issues": ["Architecture must be an object."]}
    if not isinstance(architecture.get("id"), str) or not architecture["id"].strip():
        issues.append("Architecture id is required.")
    if not isinstance(architecture.get("decision_type"), str) or not architecture["decision_type"].strip():
        issues.append("Architecture decision_type is required.")
    if not isinstance(architecture.get("workers"), list) or not architecture["workers"]:
        issues.append("Architecture must define at least one worker.")
    if not isinstance(architecture.get("action_gate"), dict):
        issues.append("Architecture must define an action_gate.")
    if not isinstance(architecture.get("outcome_metrics"), list) or not architecture["outcome_metrics"]:
        issues.append("Architecture must define outcome_metrics.")

    for worker in architecture.get("workers", []):
        result = validate_worker_contract(
            {
                "architecture_id": architecture.get("id"),
                "risk_level": architecture.get("risk_level"),
                **worker,
            }
        )
        for issue in result["issues"]:
            issues.append(f"{worker.get('worker_id', 'unknown worker')}: {issue}")

    return {"valid": not issues, "issues": issues}


def validate_contract_file(file_path: Path) -> dict[str, Any]:
    return validate_worker_contract(json.loads(file_path.read_text(encoding="utf-8")))
