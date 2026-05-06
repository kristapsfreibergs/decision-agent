from __future__ import annotations

from typing import Any

# Procurement domain worker catalog.
# Shape: funnel — intake runs in parallel (requirement analyst + market scout + risk assessor),
# then evaluator narrows the field, then a human-gated recommender produces the final brief.
#
# Governance properties:
# - Evidence hierarchy: signed contracts and specs beat vendor claims; model inference is blocked
#   from being cited as a source.
# - Conflict rule: legal/compliance constraints override cost optimisation.
# - Action gate: always human — no AI commits spend or vendor selection autonomously.

DOMAIN_ID = "procurement"

# Evidence authority weights used by the evaluator to score and rank options.
# Workers must declare which sources informed each claim in their output.
EVIDENCE_PROFILE = {
    "required_sources": [
        "requirement_spec",
        "vendor_proposals",
        "budget_constraints",
        "compliance_rules",
    ],
    "authority_weights": {
        "signed_contract":       1.00,  # highest — legally binding
        "approved_spec":         0.95,  # signed-off requirements document
        "compliance_rule":       0.95,  # legal / regulatory constraint
        "budget_approval":       0.90,  # approved budget ceiling
        "vendor_proposal":       0.70,  # vendor's own submission — verify independently
        "market_benchmark":      0.65,  # published industry pricing / benchmarks
        "reference_check":       0.60,  # third-party reference on vendor performance
        "analyst_estimate":      0.40,  # researched but unverified estimate
        "model_inference":       0.00,  # BLOCKED — may not be cited as evidence
    },
    "conflict_rules": [
        "Legal and compliance constraints override cost optimisation. If a vendor fails a compliance check, it is eliminated regardless of price.",
        "Approved specification overrides verbal clarifications. Changes to scope require a new spec.",
        "Budget ceiling is a hard cap, not a negotiating target. Options above budget are eliminated before scoring.",
        "Model inference may not be cited as a source in evaluator output. All claims must trace to a declared source with authority weight > 0.",
    ],
}

# Action gate: procurement decisions are always escalated to a human.
# The system produces a scored recommendation brief, never a binding commitment.
ACTION_GATE = {
    "type": "human_gate",
    "automatic_final_action": False,
    "requires_human_review": True,
    "rule": (
        "The recommender output is a decision brief for human review. "
        "No vendor selection, contract initiation, or spend commitment may occur "
        "without explicit human approval. The system is advisory only."
    ),
}

WORKER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "requirement_analyst",
        "phase": "intake",
        "parallelizable": True,
        "role": "requirement_analyst",
        "goal_template": (
            "Extract and structure the procurement requirements from the task. "
            "Identify: what is being procured (goods, services, or works), quantity, "
            "quality standards, delivery timeline, budget ceiling, and any mandatory "
            "compliance requirements (legal, regulatory, or organisational policy). "
            "Flag any gaps that would block evaluation. "
            "Read knowledge/procurement/requirements/ for templates and past specs."
        ),
        "read_paths": ["knowledge/procurement/requirements/**"],
        "write_paths": ["data/runs/{run_id}/workspace/requirements.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_fields": [
            "summary",
            "procurement_subject",
            "quantity_and_quality",
            "delivery_timeline",
            "budget_ceiling",
            "compliance_requirements",
            "gaps",
        ],
    },
    {
        "id": "market_scout",
        "phase": "intake",
        "parallelizable": True,
        "role": "market_scout",
        "goal_template": (
            "Research the supply market for this procurement. "
            "Find: who the active vendors are, typical market pricing and lead times, "
            "any supply constraints or monopoly risks, and recent procurement outcomes "
            "for similar items. Use web search if available, fall back to "
            "knowledge/procurement/markets/ otherwise. "
            "Do not infer vendor capabilities — only report what can be sourced."
        ),
        "read_paths": ["knowledge/procurement/markets/**"],
        "write_paths": ["data/runs/{run_id}/workspace/market_research.md"],
        "allowed_tools": ["read_file", "write_file", "list_files", "web_search"],
        "validators": ["write_scope"],
        "output_fields": [
            "summary",
            "active_vendors",
            "market_price_range",
            "lead_time_range",
            "supply_risks",
            "comparable_procurements",
        ],
    },
    {
        "id": "risk_assessor",
        "phase": "intake",
        "parallelizable": True,
        "role": "risk_assessor",
        "goal_template": (
            "Assess the risk profile of this procurement. "
            "Consider: vendor concentration risk (single-source dependency), "
            "delivery risk (tight timeline vs market lead times), "
            "compliance risk (regulatory exposure if requirements are not met), "
            "budget risk (market prices vs ceiling), and reputational risk. "
            "Rate each risk LOW / MEDIUM / HIGH with a one-line justification. "
            "Read knowledge/procurement/risk-register/ for past risk decisions."
        ),
        "read_paths": ["knowledge/procurement/risk-register/**"],
        "write_paths": ["data/runs/{run_id}/workspace/risk_assessment.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_fields": [
            "summary",
            "vendor_concentration_risk",
            "delivery_risk",
            "compliance_risk",
            "budget_risk",
            "reputational_risk",
            "overall_risk_rating",
        ],
    },
    {
        "id": "evaluator",
        "phase": "evaluate",
        "parallelizable": False,
        "role": "evaluator",
        "goal_template": (
            "Evaluate and score candidate vendors or options against the requirements. "
            "Step 1 — elimination: remove any vendor that fails a compliance requirement "
            "or exceeds the budget ceiling. These are hard eliminations; do not score them. "
            "Step 2 — scoring: for each surviving vendor, score on price (vs market benchmark), "
            "delivery (vs required timeline), quality evidence, and compliance track record. "
            "For every score claim, cite the source and its authority weight. "
            "Model inference has authority weight 0.00 and may not be cited. "
            "Step 3 — shortlist: select the top 1-3 vendors with highest weighted scores. "
            "Read requirements, market research, and risk assessment before scoring."
        ),
        "read_paths": [
            "data/runs/{run_id}/workspace/requirements.md",
            "data/runs/{run_id}/workspace/market_research.md",
            "data/runs/{run_id}/workspace/risk_assessment.md",
            "knowledge/procurement/evaluation-criteria/**",
        ],
        "write_paths": ["data/runs/{run_id}/workspace/evaluation.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope", "evidence_sources_declared"],
        "output_fields": [
            "summary",
            "eliminated_vendors",
            "scored_vendors",
            "shortlist",
            "evidence_sources",
        ],
    },
    {
        "id": "recommender",
        "phase": "recommend",
        "parallelizable": False,
        "role": "recommender",
        "goal_template": (
            "Produce the final procurement recommendation brief for human review. "
            "The brief must include: recommended vendor(s) from the shortlist with ranked reasoning, "
            "key risks and mitigations from the risk assessment, "
            "suggested contract terms or conditions to protect against identified risks, "
            "and a clear statement of what the human decision-maker must approve. "
            "Do not commit to any vendor or spend. This is a decision brief, not a decision. "
            "The human makes the final call."
        ),
        "read_paths": [
            "data/runs/{run_id}/workspace/requirements.md",
            "data/runs/{run_id}/workspace/evaluation.md",
            "data/runs/{run_id}/workspace/risk_assessment.md",
        ],
        "write_paths": ["data/runs/{run_id}/workspace/recommendation_brief.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_fields": [
            "summary",
            "recommended_vendor",
            "ranking_reasoning",
            "key_risks",
            "suggested_contract_conditions",
            "decision_required",
        ],
    },
]

DEPENDENCIES = [
    {"from": "evaluator",   "on": "requirement_analyst", "reason": "Evaluator needs structured requirements before scoring."},
    {"from": "evaluator",   "on": "market_scout",        "reason": "Evaluator needs market data to score price and lead time."},
    {"from": "evaluator",   "on": "risk_assessor",       "reason": "Evaluator needs risk ratings to weight vendor scores."},
    {"from": "recommender", "on": "evaluator",           "reason": "Recommender works from the scored shortlist."},
]

PHASES = [
    {"id": "intake",    "done_means": "Requirements, market research, and risk assessment complete.", "parallelizable": True},
    {"id": "evaluate",  "done_means": "Vendors eliminated, scored, and shortlisted.",                 "parallelizable": False},
    {"id": "recommend", "done_means": "Decision brief produced and ready for human review.",          "parallelizable": False},
]


def build_procurement_decomposition(task: dict[str, Any], run_id: str) -> dict[str, Any]:
    packages = []
    for worker in WORKER_CATALOG:
        read_paths  = [p.replace("{run_id}", run_id) for p in worker["read_paths"]]
        write_paths = [p.replace("{run_id}", run_id) for p in worker["write_paths"]]
        output_fields = worker["output_fields"]
        scalar_fields = {
            "summary", "procurement_subject", "overall_risk_rating",
            "recommended_vendor", "ranking_reasoning", "decision_required",
        }
        packages.append({
            "id": worker["id"],
            "phase_id": worker["phase"],
            "worker_role": worker["role"],
            "work_layer": worker["phase"],
            "goal": worker["goal_template"],
            "read_paths": read_paths,
            "write_paths": write_paths,
            "allowed_tools": worker["allowed_tools"],
            "validators": worker["validators"],
            "output_schema": {
                "type": "object",
                "required": output_fields,
                "properties": {
                    f: {"type": "string" if f in scalar_fields else "array"}
                    for f in output_fields
                },
            },
            "completion_contract": f"Return {', '.join(output_fields)}.",
        })

    return {
        "domain": DOMAIN_ID,
        "task_subtype": "procurement",
        "affected_surfaces": [],
        "repo_context": {},
        "packages": packages,
        "dependencies": DEPENDENCIES,
        "human_questions": [],
        "evidence_profile": EVIDENCE_PROFILE,
        "action_gate": ACTION_GATE,
        "package_outline": [
            {"id": p["id"], "work_layer": p["work_layer"], "phase_id": p["phase_id"]}
            for p in packages
        ],
        "worker_count_reasoning": {
            "total_workers": len(packages),
            "reason": (
                "requirement_analyst + market_scout + risk_assessor run in parallel during intake; "
                "evaluator scores and shortlists vendors using all three inputs; "
                "recommender produces a human-gated decision brief."
            ),
            "task_subtype": "procurement",
            "affected_surfaces": [],
        },
    }
