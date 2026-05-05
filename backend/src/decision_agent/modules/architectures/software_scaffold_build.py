from __future__ import annotations

COMMON_TOOLS = ["read_file", "write_file", "list_files", "run_tests"]

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
    "workers": [
        {
            "worker_id": "architecture_doc_worker",
            "layer": "architecture",
            "work_layer": "logic",
            "goal": (
                "Define the project architecture, hard rules, module boundaries, decision "
                "concepts, and extension path."
            ),
            "read_paths": ["README.md", "ARCHITECTURE.md", "literature/**"],
            "write_paths": ["ARCHITECTURE.md", "docs/adr/**"],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "max_steps": 5,
            "validators": ["write_scope", "architecture_rules_present", "no_provider_lock_in"],
            "output_schema": {
                "type": "object",
                "required": ["summary", "files_changed", "architecture_decisions"],
                "properties": {
                    "summary": {"type": "string"},
                    "files_changed": {"type": "array", "items": {"type": "string"}},
                    "architecture_decisions": {"type": "array", "items": {"type": "string"}},
                },
            },
            "completion_contract": (
                "Return architecture decisions and changed files. Do not implement runtime code."
            ),
        },
        {
            "worker_id": "decision_kernel_worker",
            "layer": "decision_kernel",
            "work_layer": "api",
            "goal": (
                "Implement or refine decision routing, architecture registry, run creation, "
                "and contract generation."
            ),
            "read_paths": ["ARCHITECTURE.md", "backend/src/**", "examples/**"],
            "write_paths": ["backend/src/**", "examples/**"],
            "allowed_tools": COMMON_TOOLS,
            "max_steps": 8,
            "validators": ["write_scope", "schema", "unit_tests"],
            "output_schema": {
                "type": "object",
                "required": ["summary", "files_changed", "public_api"],
                "properties": {
                    "summary": {"type": "string"},
                    "files_changed": {"type": "array", "items": {"type": "string"}},
                    "public_api": {"type": "array", "items": {"type": "string"}},
                },
            },
            "completion_contract": (
                "Return public functions and changed files. Do not add provider-specific model code."
            ),
        },
        {
            "worker_id": "knowledge_profile_worker",
            "layer": "knowledge",
            "work_layer": "data",
            "goal": "Design the evidence profile and authority-scoring interfaces.",
            "read_paths": ["ARCHITECTURE.md", "backend/src/**"],
            "write_paths": ["backend/src/decision_agent/modules/knowledge/**", "docs/adr/**"],
            "allowed_tools": COMMON_TOOLS,
            "max_steps": 6,
            "validators": ["write_scope", "authority_scores_present", "unit_tests"],
            "output_schema": {
                "type": "object",
                "required": ["summary", "files_changed", "authority_model"],
                "properties": {
                    "summary": {"type": "string"},
                    "files_changed": {"type": "array", "items": {"type": "string"}},
                    "authority_model": {"type": "object"},
                },
            },
            "completion_contract": (
                "Return authority model fields and changed files. Do not implement unrelated retrieval providers."
            ),
        },
        {
            "worker_id": "outcome_memory_worker",
            "layer": "outcome_memory",
            "work_layer": "data",
            "goal": "Implement or refine audit records, append-only outcome memory, and run metadata.",
            "read_paths": ["ARCHITECTURE.md", "backend/src/**", "data/runs/**"],
            "write_paths": [
                "backend/src/decision_agent/modules/outcomes/**",
                "backend/src/decision_agent/shared/audit_log.py",
                "docs/adr/**",
            ],
            "allowed_tools": COMMON_TOOLS,
            "max_steps": 6,
            "validators": ["write_scope", "append_only_outcomes", "unit_tests"],
            "output_schema": {
                "type": "object",
                "required": ["summary", "files_changed", "audit_fields"],
                "properties": {
                    "summary": {"type": "string"},
                    "files_changed": {"type": "array", "items": {"type": "string"}},
                    "audit_fields": {"type": "array", "items": {"type": "string"}},
                },
            },
            "completion_contract": (
                "Return audit fields and changed files. Do not create an action executor."
            ),
        },
        {
            "worker_id": "test_worker",
            "layer": "validation",
            "work_layer": "infra",
            "goal": "Add focused tests for architecture validation, contract generation, and CLI behavior.",
            "read_paths": ["backend/src/**", "examples/**", "backend/tests/**", "package.json"],
            "write_paths": ["backend/tests/**"],
            "allowed_tools": ["read_file", "write_file", "list_files", "run_tests"],
            "max_steps": 6,
            "validators": ["write_scope", "tests_run"],
            "output_schema": {
                "type": "object",
                "required": ["summary", "files_changed", "test_commands"],
                "properties": {
                    "summary": {"type": "string"},
                    "files_changed": {"type": "array", "items": {"type": "string"}},
                    "test_commands": {"type": "array", "items": {"type": "string"}},
                },
            },
            "completion_contract": (
                "Return test commands and changed files. Do not modify production code unless reassigned."
            ),
        },
    ],
}

