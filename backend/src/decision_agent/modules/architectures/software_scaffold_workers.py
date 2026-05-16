from __future__ import annotations

COMMON_TOOLS = ["read_file", "write_file", "list_files", "run_tests"]

SOFTWARE_SCAFFOLD_WORKERS = [
        {
            "worker_id": "architecture_doc_worker",
            "layer": "architecture",
            "work_layer": "logic",
            "goal": (
                "Define the project architecture, hard rules, module boundaries, decision "
                "concepts, and extension path."
            ),
            "read_paths": ["archive/docs/README.md", "archive/docs/ARCHITECTURE.md", "archive/literature/**"],
            "write_paths": ["archive/docs/ARCHITECTURE.md", "archive/docs/adr/**"],
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
            "read_paths": ["archive/docs/ARCHITECTURE.md", "backend/src/**", "examples/**"],
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
            "read_paths": ["archive/docs/ARCHITECTURE.md", "backend/src/**"],
            "write_paths": ["backend/src/decision_agent/modules/knowledge/**", "archive/docs/adr/**"],
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
            "read_paths": ["archive/docs/ARCHITECTURE.md", "backend/src/**", "archive/data/runs/**"],
            "write_paths": [
                "backend/src/decision_agent/modules/outcomes/**",
                "backend/src/decision_agent/shared/audit_log.py",
                "archive/docs/adr/**",
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
            "read_paths": ["backend/src/**", "examples/**", "tests/**", "package.json"],
            "write_paths": ["tests/**"],
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
    ]
