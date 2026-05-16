from __future__ import annotations

from typing import Any

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
            "Read archive/knowledge/procurement/2_requirements/ for templates and past specs."
        ),
        "read_paths": ["archive/knowledge/procurement/2_requirements/**"],
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
        "allowed_tables": [
            "vendor_mgmt.proposals",
            "vendor_mgmt.rankings",
            "market_intel.benchmarks",
            "compliance.certifications",
        ],
        "goal_template": (
            "Research the supply market for this procurement. "
            "Find: who the active vendors are, typical market pricing and lead times, "
            "any supply constraints or monopoly risks, and recent procurement outcomes "
            "for similar items. Use web search if available, fall back to "
            "archive/knowledge/procurement/3_offers/ otherwise. "
            "Do not infer vendor capabilities — only report what can be sourced."
        ),
        "read_paths": ["archive/knowledge/procurement/3_offers/**"],
        "write_paths": ["data/runs/{run_id}/workspace/market_research.md"],
        "allowed_tools": ["read_file", "write_file", "list_files", "web_search", "query_sql"],
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
            "Read archive/knowledge/procurement/4_context/ for past risk decisions."
        ),
        "read_paths": ["archive/knowledge/procurement/4_context/**"],
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
        "dar_action_type": "score_vendors",
        "allowed_tables": [
            "vendor_mgmt.proposals",
            "vendor_mgmt.rankings",
            "compliance.certifications",
            "finance.approved_budgets",
            "market_intel.benchmarks",
        ],
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
            "archive/knowledge/procurement/2_requirements/**",
        ],
        "write_paths": ["data/runs/{run_id}/workspace/evaluation.md"],
        "allowed_tools": ["read_file", "write_file", "list_files", "query_sql", "memory_search"],
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
        "dar_action_type": "publish_recommendation",
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
