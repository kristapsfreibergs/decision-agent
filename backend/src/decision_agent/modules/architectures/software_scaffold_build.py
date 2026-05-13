from __future__ import annotations

from decision_agent.modules.architectures.software_scaffold_workers import SOFTWARE_SCAFFOLD_WORKERS

SOFTWARE_SCAFFOLD_BUILD = {
    "id": "software-scaffold-build/v1",
    "decision_type": "software_project_build_task",
    "risk_level": "medium",
    "purpose": (
        "Coordinate bounded workers to build or modify a software project while preserving "
        "ownership, validation, and auditability."
    ),
    "evidence_profile": {
        "required_sources": ["project_architecture", "existing_files", "task_request"],
        "authority_weights": {
            "architecture_doc": 0.95,
            "existing_code": 0.9,
            "tests": 0.9,
            "user_request": 0.85,
            "generated_plan": 0.45,
            "model_inference": 0.2,
        },
        "conflict_rules": [
            "Existing architecture rules override generated plans.",
            "Tests and executable checks override model claims.",
            "Workers may not write outside declared ownership.",
        ],
    },
    "layers": [
        {
            "id": "architecture",
            "title": "Architecture Definition",
            "purpose": "Define module boundaries, hard rules, and decision concepts.",
        },
        {
            "id": "decision_kernel",
            "title": "Decision Kernel",
            "purpose": "Classify tasks, select architectures, and instantiate worker contracts.",
        },
        {
            "id": "knowledge",
            "title": "Knowledge and Evidence",
            "purpose": "Define evidence profiles and authority scoring.",
        },
        {
            "id": "outcome_memory",
            "title": "Audit and Outcome Memory",
            "purpose": "Record run history, decisions, and consequences.",
        },
        {
            "id": "validation",
            "title": "Validation",
            "purpose": "Check contracts, scopes, schemas, and test coverage.",
        },
        {
            "id": "integration_gate",
            "title": "Integration Gate",
            "purpose": "Decide what can be accepted, merged, or escalated.",
        },
    ],
    "work_layers": [
        {
            "id": "data",
            "title": "Data layer",
            "purpose": "Data models, storage rules, migrations, and persistence boundaries.",
        },
        {
            "id": "api",
            "title": "API layer",
            "purpose": "HTTP/API contracts, request validation, and service boundaries.",
        },
        {
            "id": "logic",
            "title": "Logic layer",
            "purpose": "Domain decisions, orchestration, and model-agnostic runtime logic.",
        },
        {
            "id": "ui",
            "title": "UI layer",
            "purpose": "Operator cockpit, status visibility, and human-in-the-loop controls.",
        },
        {
            "id": "infra",
            "title": "Infra",
            "purpose": "Runtime scripts, deployment shape, logging, and operational checks.",
        },
    ],
    "action_gate": {
        "type": "integration_gate",
        "automatic_final_action": False,
        "requires_human_review": True,
        "rule": "Worker outputs may be proposed, but integration requires review and validation.",
    },
    "outcome_metrics": [
        "contracts_valid",
        "scope_violations",
        "tests_passed",
        "integration_accepted",
        "rework_required",
    ],
    "workers": SOFTWARE_SCAFFOLD_WORKERS,
}
