from __future__ import annotations

DOMAIN_ID = "procurement"

DETECTION_KEYWORDS = ("procure", "procurement", "vendor", "supplier", "tender", "rfp", "rfq", "purchase", "sourcing", "contract award", "buy ")

DOMAIN_SPEC = {
    "goal_structure": {
        "shape": "funnel",
        "modifiers": ["human_gate_required", "high_risk"],
        "reasoning": (
            "Procurement decisions funnel many vendor options through elimination and "
            "scoring to a single human-approved recommendation."
        ),
    },
    "topology": {
        "shape": "funnel",
        "phases": [
            {"id": "intake",    "slot": "parallel_intake",  "parallelizable": True,  "done_means": "Requirements, market research, and risk assessment complete."},
            {"id": "evaluate",  "slot": "evaluate_vendors",  "parallelizable": False, "done_means": "Vendors eliminated, scored, and shortlisted."},
            {"id": "recommend", "slot": "recommend",         "parallelizable": False, "done_means": "Decision brief produced and ready for human review."},
        ],
        "dependency_model": "intake workers run in parallel; evaluator waits on all three; recommender waits on evaluator",
        "completion_semantics": "done means recommendation_brief.md is produced and a human has reviewed it",
        "gates": [{"id": "human_gate", "placement": "recommend", "rule": "Human approval required before any vendor commitment or spend."}],
        "topology_reasoning": "Procurement domain: parallel intake (requirements + market + risk) feeds evaluator, then human-gated recommender.",
    },
}

EVIDENCE_PROFILE = {
    "required_sources": [
        "requirement_spec",
        "vendor_proposals",
        "budget_constraints",
        "compliance_rules",
    ],
    "authority_weights": {
        "signed_contract":       1.00,
        "approved_spec":         0.95,
        "compliance_rule":       0.95,
        "budget_approval":       0.90,
        "vendor_proposal":       0.70,
        "market_benchmark":      0.65,
        "reference_check":       0.60,
        "analyst_estimate":      0.40,
        "model_inference":       0.00,
    },
    "conflict_rules": [
        "Legal and compliance constraints override cost optimisation. If a vendor fails a compliance check, it is eliminated regardless of price.",
        "Approved specification overrides verbal clarifications. Changes to scope require a new spec.",
        "Budget ceiling is a hard cap, not a negotiating target. Options above budget are eliminated before scoring.",
        "Model inference may not be cited as a source in evaluator output. All claims must trace to a declared source with authority weight > 0.",
    ],
    "min_avg_score": 0.5,
    "min_individual_score": 0.25,
    "temporal_half_life_days": 365,
}

SCOPE_PROFILE = {
    "allowed_evidence_classes": [
        name for name, weight in EVIDENCE_PROFILE["authority_weights"].items()
        if float(weight) > 0.0
    ],
    "required_evidence_classes": [
        "compliance_rule",
        "vendor_proposal",
    ],
    "out_of_scope_markers": [
        "personal_opinion",
        "competitor_smear",
        "rumor",
    ],
    "scope_phrase_blocklist": [
        "i think",
        "in my opinion",
        "i feel that",
        "my gut says",
        "i suspect",
        "rumor has it",
    ],
}

CONSEQUENCE_TABLE = {
    "produce_brief":           "INTERNAL_REVERSIBLE",
    "score_vendors":           "INTERNAL_REVERSIBLE",
    "shortlist_vendors":       "INTERNAL_REVERSIBLE",
    "publish_recommendation":  "EXTERNAL_VISIBLE",
    "notify_vendor":           "EXTERNAL_VISIBLE",
    "select_vendor":           "IRREVERSIBLE",
    "commit_spend":            "IRREVERSIBLE",
    "award_contract":          "IRREVERSIBLE",
}

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
