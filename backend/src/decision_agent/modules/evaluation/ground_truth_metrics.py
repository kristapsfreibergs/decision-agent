from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.evaluation.metric_loaders import _list_outputs, _read_json


def evaluate_ground_truth(
    run_dir: Path,
    ground_truth: dict[str, Any],
) -> dict[str, Any]:
    """Compare run outputs against ground truth. Returns metric dict."""
    metrics: dict[str, Any] = {}
    outputs = dict(_list_outputs(run_dir))

    metrics["gt_vendor_correct"] = _check_vendor(outputs, ground_truth)
    metrics["gt_eliminations_correct"] = _check_eliminations(outputs, ground_truth)
    metrics["gt_escalation_correct"] = _check_escalation(outputs, ground_truth)
    metrics["gt_constraints_detected"] = _check_constraints(outputs, ground_truth)
    metrics["gt_outcome_correct"] = _check_outcome(outputs, ground_truth)

    # Composite: fraction of ground truth checks that passed
    checks = [
        metrics["gt_vendor_correct"],
        metrics["gt_eliminations_correct"],
        metrics["gt_escalation_correct"],
        metrics["gt_outcome_correct"],
    ]
    passed = sum(1 for c in checks if c)
    metrics["gt_accuracy"] = round(passed / len(checks), 4)

    return metrics


def _check_vendor(outputs: dict[str, Any], gt: dict[str, Any]) -> bool:
    """Did the system recommend an acceptable vendor?"""
    acceptable = {v.lower() for v in gt.get("acceptable_vendors", [])}
    if not acceptable:
        # No acceptable vendor means no vendor should be recommended
        rec = outputs.get("recommender", {})
        vendor = str(rec.get("recommended_vendor", "")).strip().lower()
        return vendor == "" or "none" in vendor or "no vendor" in vendor

    rec = outputs.get("recommender", {})
    vendor = str(rec.get("recommended_vendor", "")).strip().lower()
    return any(a in vendor for a in acceptable)


def _check_eliminations(outputs: dict[str, Any], gt: dict[str, Any]) -> bool:
    """Did the system eliminate the expected vendors?"""
    expected = gt.get("expected_eliminations", [])
    if not expected:
        return True

    evaluator = outputs.get("evaluator", {})
    eliminated_raw = evaluator.get("eliminated_vendors", [])
    eliminated_text = " ".join(str(v).lower() for v in eliminated_raw)

    found = 0
    for entry in expected:
        vendor = entry["vendor"].lower() if isinstance(entry, dict) else str(entry).lower()
        if vendor in eliminated_text:
            found += 1
    return found == len(expected)


def _check_escalation(outputs: dict[str, Any], gt: dict[str, Any]) -> bool:
    """Did the system correctly escalate (or not)?"""
    expected = gt.get("expected_escalation", False)

    rec = outputs.get("recommender", {})
    # Check various signals of escalation
    text = json.dumps(rec).lower() if rec else ""
    escalated = (
        "escalat" in text
        or "no vendor" in text
        or "cannot recommend" in text
        or rec.get("recommended_vendor", "") in ("", "none", "None", None)
    )
    return escalated == expected


def _check_constraints(outputs: dict[str, Any], gt: dict[str, Any]) -> float:
    """Fraction of must_detect_constraints found across all outputs."""
    constraints = gt.get("must_detect_constraints", [])
    if not constraints:
        return 1.0

    all_text = " ".join(
        json.dumps(output).lower() for output in outputs.values()
    )

    found = 0
    for constraint in constraints:
        # Normalize: "budget_ceiling" → ["budget", "ceiling"]
        terms = constraint.lower().replace("_", " ").split()
        if all(term in all_text for term in terms):
            found += 1
    return round(found / len(constraints), 4)


def _check_outcome(outputs: dict[str, Any], gt: dict[str, Any]) -> bool:
    """Did the system produce the expected outcome type?"""
    expected = gt.get("expected_outcome", "")
    if not expected:
        return True

    rec = outputs.get("recommender", {})
    vendor = str(rec.get("recommended_vendor", "")).strip()

    if expected == "recommend_vendor":
        return vendor != "" and vendor.lower() not in ("none", "no vendor", "")
    if expected == "escalate":
        text = json.dumps(rec).lower() if rec else ""
        return (
            vendor in ("", "none", "None", None)
            or "escalat" in text
            or "no vendor" in text
            or "cannot recommend" in text
        )
    return True


# Needed for json.dumps in the functions above
import json
