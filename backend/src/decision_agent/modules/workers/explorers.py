from __future__ import annotations

from typing import Any


EXPLORER_CATALOG: dict[str, dict[str, Any]] = {
    "codebase_explorer": {
        "id": "codebase_explorer",
        "phase": "intake",
        "parallelizable": True,
        "role": "codebase_explorer",
        "goal_template": (
            "Explore the project codebase to build context for the task: {task_context}. "
            "Use list_files to map the directory structure. Use read_file to read key files "
            "(entry points, relevant modules, existing patterns). "
            "Summarise: what the project does, which files are most relevant to the task, "
            "and what existing patterns or conventions the implementers must follow. "
            "Write your findings to data/runs/{run_id}/workspace/codebase_context.md."
        ),
        "read_paths": ["backend/src/**", "public/**", "docs/**", "README.md", "ARCHITECTURE.md"],
        "write_paths": ["data/runs/{run_id}/workspace/codebase_context.md"],
        "allowed_tools": ["read_file", "list_files", "write_file"],
        "output_fields": ["summary", "relevant_files", "patterns", "context_path"],
        "scalar_fields": {"summary", "context_path"},
    },
    "web_researcher": {
        "id": "web_researcher",
        "phase": "intake",
        "parallelizable": True,
        "role": "web_researcher",
        "goal_template": (
            "Research current information needed for the task: {task_context}. "
            "Search for relevant documentation, standards, pricing, or recent developments. "
            "Write your findings to data/runs/{run_id}/workspace/research.md."
        ),
        "read_paths": [],
        "write_paths": ["data/runs/{run_id}/workspace/research.md"],
        "allowed_tools": ["web_search", "write_file"],
        "output_fields": ["summary", "sources", "findings", "research_path"],
        "scalar_fields": {"summary", "research_path"},
    },
    "document_reader": {
        "id": "document_reader",
        "phase": "intake",
        "parallelizable": True,
        "role": "document_reader",
        "goal_template": (
            "Read project documents and specifications relevant to: {task_context}. "
            "Look in docs/** and literature/** for source material, requirements, and constraints. "
            "Summarise what downstream workers need to know and write it to "
            "data/runs/{run_id}/workspace/document_context.md."
        ),
        "read_paths": ["docs/**", "literature/**"],
        "write_paths": ["data/runs/{run_id}/workspace/document_context.md"],
        "allowed_tools": ["read_file", "list_files", "write_file"],
        "output_fields": ["summary", "relevant_documents", "key_requirements", "context_path"],
        "scalar_fields": {"summary", "context_path"},
    },
    "knowledge_reader": {
        "id": "knowledge_reader",
        "phase": "intake",
        "parallelizable": True,
        "role": "knowledge_reader",
        "goal_template": (
            "Read the project knowledge store for context relevant to: {task_context}. "
            "Look in knowledge/** for past decisions, preferences, and conventions. "
            "Summarise what is relevant and write to data/runs/{run_id}/workspace/knowledge_context.md."
        ),
        "read_paths": ["knowledge/**"],
        "write_paths": ["data/runs/{run_id}/workspace/knowledge_context.md"],
        "allowed_tools": ["read_file", "list_files", "write_file"],
        "output_fields": ["summary", "relevant_entries", "context_path"],
        "scalar_fields": {"summary", "context_path"},
    },
}


def build_explorer_package(explorer_id: str, run_id: str, task_context: str) -> dict[str, Any]:
    """Instantiate an explorer spec into a package dict."""
    spec = EXPLORER_CATALOG[explorer_id]
    read_paths = [path.replace("{run_id}", run_id) for path in spec["read_paths"]]
    write_paths = [path.replace("{run_id}", run_id) for path in spec["write_paths"]]
    goal = (
        spec["goal_template"]
        .replace("{task_context}", task_context)
        .replace("{run_id}", run_id)
    )
    output_fields = spec["output_fields"]
    scalar_fields = spec.get("scalar_fields", set())
    return {
        "id": explorer_id,
        "worker_id": explorer_id,
        "phase_id": "intake",
        "worker_role": spec["role"],
        "work_layer": "intake",
        "goal": goal,
        "read_paths": read_paths,
        "write_paths": write_paths,
        "allowed_tools": spec["allowed_tools"],
        "validators": ["write_scope"],
        "output_schema": {
            "type": "object",
            "required": output_fields,
            "properties": {
                field: {"type": "string" if field in scalar_fields else "array"}
                for field in output_fields
            },
        },
        "completion_contract": f"Return {', '.join(output_fields)}.",
    }
