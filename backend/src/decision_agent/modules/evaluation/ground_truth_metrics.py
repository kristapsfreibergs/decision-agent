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
    metrics["vendors_considered"] = _count_vendors_considered(outputs, ground_truth)
    metrics["recommended_vendor"] = _extract_recommended_vendor(outputs)
    metrics["winner_scores"] = _extract_winner_scores(outputs, metrics["recommended_vendor"])

    # Composite: fraction of ground truth checks that passed
    checks = [
        metrics["gt_vendor_correct"],
        metrics["gt_eliminations_correct"],
        metrics["gt_outcome_correct"],
    ]
    passed = sum(1 for c in checks if c)
    metrics["gt_accuracy"] = round(passed / len(checks), 4)

    return metrics


def _get_rec(outputs: dict[str, Any]) -> dict[str, Any]:
    """Get recommendation output, supporting both legacy (recommender) and graph (recommendation) keys.

    Graph executor wraps agent output under an 'output' key:
    {"agent_id": "recommendation", "success": true, "output": {...}}
    """
    raw = outputs.get("recommender") or outputs.get("recommendation") or {}
    # Unwrap graph executor envelope if present
    if isinstance(raw, dict) and "output" in raw and isinstance(raw["output"], dict):
        return raw["output"]
    return raw


def _get_vendor_str(rec: dict[str, Any]) -> str:
    """Extract recommended vendor string from rec dict, handling nested primary_recommendation."""
    vendor = str(rec.get("recommended_vendor", "")).strip()
    if not vendor:
        primary = rec.get("primary_recommendation", {})
        if isinstance(primary, dict):
            vendor = str(primary.get("vendor", "")).strip()
    return vendor


def _check_vendor(outputs: dict[str, Any], gt: dict[str, Any]) -> bool:
    """Did the system recommend an acceptable vendor?"""
    acceptable = {v.lower() for v in gt.get("acceptable_vendors", [])}
    rec = _get_rec(outputs)

    # Try dedicated field first (including nested), then shortlist and summary text
    vendor = _get_vendor_str(rec).lower()
    if gt.get("expected_outcome") == "escalate" and not acceptable and vendor in ("", "none", "n/a"):
        return True
    if not vendor:
        shortlist = rec.get("shortlist", [])
        if shortlist:
            vendor = str(shortlist[0]).lower()
    if not vendor:
        vendor = str(rec.get("summary", "")).lower()

    if not vendor or vendor in ("none", "n/a", ""):
        if gt.get("expected_outcome") == "escalate" and not acceptable:
            return True
        return False
    if not acceptable:
        return False
    # Extract key name tokens (e.g. "atlas", "helio") from each acceptable vendor
    # and check if any appear in the recommended vendor string
    def key_tokens(s: str) -> set:
        return {w for w in s.lower().split() if w not in ("vendor", "the", "a", "an")}
    vendor_tokens = key_tokens(vendor)
    return any(bool(key_tokens(a) & vendor_tokens) for a in acceptable)


def _check_eliminations(outputs: dict[str, Any], gt: dict[str, Any]) -> bool:
    """Did the system eliminate the expected vendors?"""
    expected = gt.get("expected_eliminations", [])
    if not expected:
        return True

    # Support legacy "evaluator" and graph "eligibility" keys; unwrap envelope if present
    raw = outputs.get("eligibility") or outputs.get("evaluator") or {}
    if isinstance(raw, dict) and "output" in raw and isinstance(raw["output"], dict):
        raw = raw["output"]
    eliminated_raw = raw.get("eliminated_vendors", raw.get("eliminated", []))
    eliminated_text = " ".join(json.dumps(v).lower() for v in eliminated_raw)

    found = 0
    for entry in expected:
        vendor = entry["vendor"].lower() if isinstance(entry, dict) else str(entry).lower()
        if vendor in eliminated_text:
            found += 1
    return found == len(expected)


def _check_escalation(outputs: dict[str, Any], gt: dict[str, Any]) -> bool:
    """Did the system correctly escalate (or not)? Returns True if not applicable."""
    expected = gt.get("expected_escalation")
    if expected is None:
        return True  # escalation not evaluated for this case study

    rec = _get_rec(outputs)
    text = json.dumps(rec).lower() if rec else ""
    vendor = _get_vendor_str(rec)
    escalated = (
        "escalat" in text
        or "no vendor" in text
        or "cannot recommend" in text
        or vendor.lower() in ("", "none", "n/a")
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

    rec = _get_rec(outputs)
    vendor = _get_vendor_str(rec)

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


def _extract_recommended_vendor(outputs: dict[str, Any]) -> str:
    """Extract the recommended vendor name from output, however it was expressed."""
    rec = _get_rec(outputs)
    vendor = _get_vendor_str(rec)
    if not vendor:
        shortlist = rec.get("shortlist", [])
        if shortlist:
            vendor = str(shortlist[0]).strip()[:80]
    return vendor or "none"


def _extract_winner_scores(outputs: dict[str, Any], recommended_vendor: str) -> dict | None:
    """Extract scores for the winning vendor from scored_vendors list."""
    if not recommended_vendor or recommended_vendor == "none":
        return None
    rec = outputs.get("recommender", {})
    scored = rec.get("scored_vendors", [])
    winner_tokens = {w for w in recommended_vendor.lower().split() if w not in ("vendor", "the")}
    for entry in scored:
        name = str(entry.get("vendor", "")).lower()
        name_tokens = {w for w in name.split() if w not in ("vendor", "the")}
        if winner_tokens & name_tokens:
            return {
                "price_score": entry.get("price_score"),
                "delivery_score": entry.get("delivery_score"),
                "quality_score": entry.get("quality_score"),
                "compliance_score": entry.get("compliance_score"),
            }
    return None


def _count_vendors_considered(outputs: dict[str, Any], gt: dict[str, Any]) -> int:
    """Count how many vendors from the ground truth list appear anywhere in the output."""
    all_vendors = set()
    for v in gt.get("acceptable_vendors", []):
        name = v.lower()
        all_vendors.add(name)
        all_vendors.add(name.replace("vendor ", ""))  # "atlas" matches "vendor atlas"
    for entry in gt.get("expected_eliminations", []):
        name = (entry["vendor"].lower() if isinstance(entry, dict) else str(entry).lower())
        all_vendors.add(name)
        all_vendors.add(name.replace("vendor ", ""))

    all_text = " ".join(json.dumps(o).lower() for o in outputs.values())
    # Count each vendor once (use the short name as canonical)
    canonical = {v.replace("vendor ", "") for v in all_vendors}
    return sum(1 for v in canonical if v in all_text)


# Needed for json.dumps in the functions above
import json
