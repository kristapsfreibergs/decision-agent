from __future__ import annotations

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read a file from the project. Path must be within contract read_paths.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Path must be within contract write_paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files matching a glob pattern. Pattern must be within contract read_paths.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the project test suite. Command must be one of the approved test commands.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for current information. Not implemented in the local tool provider yet.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "memory_search",
        "description": (
            "Search past decision runs for relevant evidence within the current scope. "
            "Returns evidence items from previous completed runs that match the query. "
            "Useful for: past vendor assessments, prior procurement outcomes, "
            "historical risk decisions. All results are scoped to the current domain."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for in past run evidence.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_agent",
        "description": (
            "Ask another agent a question about what it knows. "
            "The target agent answers from its already-completed analysis. "
            "Use this when you need information from a previous step that isn't in your workspace files. "
            "Only agents that have already completed can be asked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent to ask, e.g. 'evidence', 'requirement', 'eligibility'.",
                },
                "question": {
                    "type": "string",
                    "description": "The question to ask. Be specific about what data you need.",
                },
            },
            "required": ["agent_id", "question"],
        },
    },
    {
        "name": "query_sql",
        "description": (
            "Query a table declared in configs/data-sources/schema-map.json. "
            "Returns rows annotated as evidence sources (id, type, excerpt, created_at). "
            "The table must be in the contract's allowed_tables field. "
            "Use filters to narrow the result set. Maximum 20 rows returned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Fully qualified table name as in schema-map, e.g. 'vendor_mgmt.proposals'",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional key=value pairs for WHERE clause (equality only). e.g. {\"iso27001_certified\": 1}",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return (default 20, max 20).",
                },
            },
            "required": ["table"],
        },
    },
]
