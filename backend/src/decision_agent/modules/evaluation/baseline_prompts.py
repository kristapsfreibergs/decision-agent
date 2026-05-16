"""Static per-domain prompts and output schemas for A0 baseline conditions.

A0 uses domain-appropriate but governance-free prompts. Dynamic prompt
construction from domain parameters is a property of the governed
architecture (Step 3 onward) and is evaluated separately.

These prompts are intentionally minimal: one sentence of role context,
one instruction to output JSON. Not zero context, not optimised context.
They reflect the minimum a practitioner would write.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

A0_SYSTEM_PROMPTS: dict[str, str] = {
    "procurement": (
        "You are an expert procurement advisor. "
        "Evaluate ALL vendors listed in the knowledge files. "
        "Be extremely concise. Target under 800 output tokens total. One short phrase per vendor in eliminated_vendors, one integer score per dimension in scored_vendors. "
        "Produce a vendor recommendation as a JSON object with these fields: "
        "summary (2 sentences max), eliminated_vendors (array of strings), "
        "scored_vendors (array of {vendor, price_score, delivery_score, quality_score, compliance_score}), "
        "shortlist (array of vendor name strings only), recommended_vendor (string, vendor name only), "
        "evidence_sources (array of {id, type, excerpt} — excerpt max 20 words each). "
        "Output only the JSON object, nothing else."
    ),
    "cv_evaluation": (
        "You are an expert HR evaluator. "
        "Given a candidate CV and job specification, produce a structured evaluation as a JSON object with these fields: "
        "summary (string), requirement_scores (array of objects with requirement, score, evidence, gap), "
        "ranked_candidates (array of objects with candidate and overall_score), "
        "recommendation (string), evidence_sources (array of objects with id, type, excerpt, created_at). "
        "Output only the JSON object, nothing else."
    ),
    "construction_pricing": (
        "You are an expert quantity surveyor. "
        "Given a construction pricing task, produce a cost estimate as a JSON object with these fields: "
        "summary (string), line_items (array of objects with description, quantity, unit, unit_price, subtotal), "
        "total_estimate (number), assumptions (array of strings), "
        "evidence_sources (array of objects with id, type, excerpt, created_at). "
        "Output only the JSON object, nothing else."
    ),
}

DOMAIN_OUTPUT_SPECS: dict[str, list[str]] = {
    "procurement": [
        "summary",
        "eliminated_vendors",
        "scored_vendors",
        "shortlist",
        "evidence_sources",
    ],
    "cv_evaluation": [
        "summary",
        "requirement_scores",
        "ranked_candidates",
        "recommendation",
        "evidence_sources",
    ],
    "construction_pricing": [
        "summary",
        "line_items",
        "total_estimate",
        "assumptions",
        "evidence_sources",
    ],
}

_DEFAULT_DOMAIN = "procurement"


def detect_domain_from_fixture(fixture_id: str) -> str:
    """Derive domain from fixture filename prefix.

    Fixtures are named like procurement_laptops, cv_evaluation_senior_dev, etc.
    This is a static lookup, not a router — A0 must not use the decision router.
    """
    for domain in A0_SYSTEM_PROMPTS:
        if fixture_id.startswith(domain):
            return domain
    return _DEFAULT_DOMAIN


def get_a0_system_prompt(domain: str) -> str:
    return A0_SYSTEM_PROMPTS.get(domain, A0_SYSTEM_PROMPTS[_DEFAULT_DOMAIN])


def get_domain_output_spec(domain: str) -> list[str]:
    return DOMAIN_OUTPUT_SPECS.get(domain, DOMAIN_OUTPUT_SPECS[_DEFAULT_DOMAIN])


_MAX_FILE_CHARS = 40_000


def build_informed_context(domain: str, project_root: Path) -> str:
    """Assemble the full context that governed workers would receive.

    Includes: all worker goals and output schemas from the domain catalog,
    evidence taxonomy with authority weights, DSC scope rules, and knowledge
    files the workers would read. This is concatenated into a single context
    block so A0 receives identical information to F -- without any
    architectural enforcement.
    """
    parts: list[str] = []

    catalog, evidence_profile, scope_profile = _load_domain_artifacts(domain)

    # Worker goals and output schemas
    if catalog:
        parts.append("=== WORKER ROLES AND GOALS ===")
        for worker in catalog:
            parts.append(
                f"\nWorker: {worker['id']}\n"
                f"Role: {worker.get('role', worker['id'])}\n"
                f"Phase: {worker.get('phase', 'unknown')}\n"
                f"Goal: {worker.get('goal_template', '')}\n"
                f"Output fields: {', '.join(worker.get('output_fields', []))}"
            )

    # Evidence taxonomy
    if evidence_profile:
        weights = evidence_profile.get("authority_weights", {})
        parts.append("\n=== EVIDENCE TAXONOMY (PAAP) ===")
        parts.append("Authority weights per evidence type:")
        for etype, weight in sorted(weights.items(), key=lambda x: -x[1]):
            parts.append(f"  {etype}: {weight}")
        conflict_rules = evidence_profile.get("conflict_rules", [])
        if conflict_rules:
            parts.append("\nConflict rules:")
            for rule in conflict_rules:
                parts.append(f"  - {rule}")
        min_avg = evidence_profile.get("min_avg_score")
        if min_avg is not None:
            parts.append(f"\nMinimum average evidence score: {min_avg}")

    # DSC scope rules
    if scope_profile:
        parts.append("\n=== SCOPE RULES (DSC) ===")
        allowed = scope_profile.get("allowed_evidence_classes", [])
        if allowed:
            parts.append(f"Allowed evidence types: {', '.join(allowed)}")
        required = scope_profile.get("required_evidence_classes", [])
        if required:
            parts.append(f"Required evidence types: {', '.join(required)}")
        markers = scope_profile.get("out_of_scope_markers", [])
        if markers:
            parts.append(f"Out-of-scope markers: {', '.join(markers)}")
        phrases = scope_profile.get("scope_phrase_blocklist", [])
        if phrases:
            parts.append(f"Forbidden phrases: {', '.join(phrases)}")

    # Knowledge files — read directly from case study input/ directory
    from decision_agent.modules.evaluation.case_study import case_studies_dir, knowledge_dir as _kd
    # project_root is the run dir; derive case_id from it (input/ is at case study root)
    # Fall back: scan input/ from case studies root matching domain prefix
    input_dir = None
    cs_root = case_studies_dir()
    for case_dir in sorted(cs_root.iterdir()):
        if case_dir.is_dir() and case_dir.name.startswith(domain):
            input_dir = case_dir / "input"
            break
    if input_dir and input_dir.exists():
        parts.append("\n=== KNOWLEDGE FILES ===")
        for fpath in sorted(input_dir.rglob("*.md")):
            rel = fpath.relative_to(input_dir)
            try:
                content = fpath.read_text(encoding="utf-8")[:_MAX_FILE_CHARS]
            except OSError:
                continue
            parts.append(f"\n--- {rel} ---\n{content}")

    return "\n".join(parts)


def _load_domain_artifacts(
    domain: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Load worker catalog, evidence profile, and scope profile for a domain."""
    if domain == "procurement":
        from decision_agent.modules.architectures.domains.procurement_catalog import (
            WORKER_CATALOG,
        )
        from decision_agent.modules.architectures.domains.procurement_metadata import (
            EVIDENCE_PROFILE,
            SCOPE_PROFILE,
        )
        return WORKER_CATALOG, EVIDENCE_PROFILE, SCOPE_PROFILE
    return [], {}, {}
