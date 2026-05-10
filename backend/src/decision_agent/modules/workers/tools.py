from __future__ import annotations

import json
import os
import shlex
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable


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

AuditEmit = Callable[..., None]


def execute_tool(
    name: str,
    params: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path,
    audit_emit: AuditEmit,
) -> str:
    """Execute a tool call, enforcing contract boundaries. Returns string result."""
    allowed = contract.get("allowed_tools", [])
    if name not in allowed:
        return f"ERROR: tool '{name}' not in contract allowed_tools: {allowed}"

    if name == "read_file":
        path = str(params.get("path", ""))
        if not _within_read_paths(path, contract.get("read_paths", []), project_root):
            return f"ERROR: path '{path}' is outside contract read_paths"
        full = (project_root / path).resolve()
        if not full.exists():
            return f"ERROR: file not found: {path}"
        if not full.is_file():
            return f"ERROR: path is not a file: {path}"
        audit_emit("tool_called", tool="read_file", path=path)
        return full.read_text(encoding="utf-8", errors="replace")[:8000]

    if name == "write_file":
        path = str(params.get("path", ""))
        content = str(params.get("content", ""))
        if not _within_write_paths(path, contract.get("write_paths", []), project_root):
            return f"ERROR: path '{path}' is outside contract write_paths"
        full = (project_root / path).resolve()
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        audit_emit("tool_called", tool="write_file", path=path, bytes=len(content))
        return f"OK: wrote {len(content)} bytes to {path}"

    if name == "list_files":
        pattern = str(params.get("pattern", ""))
        if not _within_read_paths(pattern, contract.get("read_paths", []), project_root):
            return f"ERROR: pattern '{pattern}' is outside contract read_paths"
        glob_pattern = _file_glob_pattern(pattern)
        root = project_root.resolve()
        matches = sorted(
            path.resolve().relative_to(root).as_posix()
            for path in project_root.glob(glob_pattern)
            if path.is_file() and _is_under_root(path, project_root)
        )
        audit_emit("tool_called", tool="list_files", pattern=pattern, count=len(matches))
        return "\n".join(matches) if matches else "(no files matched)"

    if name == "run_tests":
        command = str(params.get("command", "npm test")).strip() or "npm test"
        result = _run_tests(command, project_root)
        audit_emit(
            "tool_called",
            tool="run_tests",
            command=command,
            returncode=result.returncode,
        )
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        return output[:8000] if output else f"Tests exited with code {result.returncode}."

    if name == "web_search":
        query = str(params.get("query", ""))
        audit_emit("tool_called", tool="web_search", query=query, supported=False)
        return (
            "web_search is not available in this environment. "
            f"Query was: '{query}'. "
            "Fall back to knowledge/procurement/markets/ for vendor and pricing data. "
            "Call list_files to discover available files, then read_file to access them."
        )

    if name == "memory_search":
        return _execute_memory_search(params, contract, project_root, audit_emit)

    if name == "query_sql":
        return _execute_query_sql(params, contract, project_root, audit_emit)

    return f"ERROR: unknown tool '{name}'"


def _execute_memory_search(
    params: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path,
    audit_emit: AuditEmit,
) -> str:
    query = str(params.get("query", "")).strip()
    limit = min(int(params.get("limit") or 10), 20)
    if not query:
        return "ERROR: memory_search requires a non-empty query."

    scope_dict = contract.get("scope_contract") or {}

    try:
        from decision_agent.shared.memory.registry import get_memory_provider
    except ImportError:
        return "ERROR: memory provider not available."

    provider = get_memory_provider(project_root / "data")
    hits = provider.search(query, scope_dict, limit=limit)
    audit_emit("tool_called", tool="memory_search", query=query, hits=len(hits))

    if not hits:
        return (
            f"No past evidence found for query '{query}' within scope. "
            "This may be the first run for this domain."
        )

    results = [
        {
            "id": h.memory_id,
            "type": h.evidence_class,
            "excerpt": h.excerpt,
            "created_at": h.created_at,
            "authority_score": h.authority_score,
            "relevance_score": h.relevance_score,
            "source_run": h.source_run_id,
            "source_worker": h.worker_id,
        }
        for h in hits
    ]
    return json.dumps(results, indent=2, ensure_ascii=False)


_SCHEMA_MAP_CACHE: dict[str, Any] | None = None


def _load_schema_map(project_root: Path) -> dict[str, Any]:
    global _SCHEMA_MAP_CACHE
    if _SCHEMA_MAP_CACHE is not None:
        return _SCHEMA_MAP_CACHE
    path = project_root / "configs" / "data-sources" / "schema-map.json"
    if not path.exists():
        return {}
    try:
        _SCHEMA_MAP_CACHE = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _SCHEMA_MAP_CACHE = {}
    return _SCHEMA_MAP_CACHE


def _execute_query_sql(
    params: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path,
    audit_emit: AuditEmit,
) -> str:
    table = str(params.get("table", "")).strip()
    filters: dict[str, Any] = params.get("filters") or {}
    limit = min(int(params.get("limit") or 20), 20)

    # DSC enforcement: table must be in contract's allowed_tables
    allowed_tables: list[str] = contract.get("allowed_tables") or []
    if allowed_tables and table not in allowed_tables:
        audit_emit("tool_called", tool="query_sql", table=table, blocked=True,
                   reason="not in allowed_tables")
        return f"ERROR: table '{table}' is not in the contract's allowed_tables: {allowed_tables}"

    schema_map = _load_schema_map(project_root)
    tables = schema_map.get("tables", {})
    if table not in tables:
        audit_emit("tool_called", tool="query_sql", table=table, blocked=True,
                   reason="not in schema-map")
        return (
            f"ERROR: table '{table}' is not in schema-map.json. "
            f"Available tables: {sorted(tables.keys())}"
        )

    table_def = tables[table]
    conn_name = table_def["connection"]
    connections = schema_map.get("connections", {})
    conn_def = connections.get(conn_name, {})

    evidence_class = table_def["evidence_class"]
    timestamp_col = table_def.get("timestamp_col")
    excerpt_cols: list[str] = table_def.get("excerpt_cols", [])
    pk_col: str = table_def.get("pk_col", "rowid")

    # Build query — only equality filters, no injection risk
    where_parts: list[str] = []
    where_values: list[Any] = []
    for col, val in filters.items():
        # Allow alphanumeric + underscore column names only (guards against injection)
        if col and all(c.isalnum() or c == "_" for c in col):
            where_parts.append(f'"{col}" = ?')
            where_values.append(val)

    sql = f'SELECT * FROM "{table}"'
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += f" LIMIT {limit}"

    try:
        if conn_def.get("type") == "sqlite":
            db_path = project_root / conn_def.get("path", "data/demo.db")
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, where_values).fetchall()
            conn.close()
        else:
            return f"ERROR: connection type '{conn_def.get('type')}' not yet supported."
    except (sqlite3.Error, OSError) as exc:
        audit_emit("tool_called", tool="query_sql", table=table, error=str(exc)[:200])
        return f"ERROR: query failed: {exc}"

    # Annotate rows as evidence sources
    evidence_sources = []
    for row in rows:
        row_dict = dict(row)
        pk_value = row_dict.get(pk_col, "unknown")
        excerpt_parts = [
            f"{col}={row_dict[col]}"
            for col in excerpt_cols
            if col in row_dict and row_dict[col] is not None
        ]
        evidence_sources.append({
            "id": f"{table}#{pk_value}",
            "type": evidence_class,
            "excerpt": "; ".join(excerpt_parts),
            "created_at": str(row_dict.get(timestamp_col, "")) if timestamp_col else None,
            "_row": row_dict,
        })

    audit_emit("tool_called", tool="query_sql", table=table,
               rows=len(evidence_sources), evidence_class=evidence_class)
    return json.dumps(evidence_sources, indent=2, ensure_ascii=False, default=str)


def _run_tests(command: str, project_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    allowed_commands = {
        "npm test": (["npm", "test"], {}),
        "python3 -m unittest discover backend/tests": (
            ["python3", "-m", "unittest", "discover", "backend/tests"],
            {"PYTHONPATH": "backend/src"},
        ),
        "PYTHONPATH=backend/src python3 -m unittest discover backend/tests": (
            ["python3", "-m", "unittest", "discover", "backend/tests"],
            {"PYTHONPATH": "backend/src"},
        ),
    }
    if command not in allowed_commands:
        return subprocess.CompletedProcess(
            args=shlex.split(command),
            returncode=2,
            stdout="",
            stderr=(
                "ERROR: run_tests command is not approved. "
                f"Allowed commands: {', '.join(sorted(allowed_commands))}"
            ),
        )

    args, extra_env = allowed_commands[command]
    env.update(extra_env)
    return subprocess.run(
        args,
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _file_glob_pattern(pattern: str) -> str:
    """Treat directory-recursive patterns like knowledge/** as file searches."""
    normalized = pattern.rstrip("/")
    if normalized.endswith("/**"):
        return f"{normalized}/*"
    return pattern


def _within_read_paths(path_or_pattern: str, read_paths: list[str], project_root: Path) -> bool:
    return _within_declared_paths(path_or_pattern, read_paths, project_root)


def _within_write_paths(path_or_pattern: str, write_paths: list[str], project_root: Path) -> bool:
    return _within_declared_paths(path_or_pattern, write_paths, project_root)


def _within_declared_paths(path_or_pattern: str, declared_paths: list[str], project_root: Path) -> bool:
    if not path_or_pattern:
        return False

    root = project_root.resolve()
    candidate = (root / path_or_pattern).resolve()
    if not _is_under_root(candidate, root):
        return False

    for declared in declared_paths:
        if not declared:
            continue
        if _matches_declared_path(path_or_pattern, candidate, declared, root):
            return True
    return False


def _matches_declared_path(path_or_pattern: str, candidate: Path, declared: str, root: Path) -> bool:
    if "*" in declared:
        # Check if candidate is under the glob's base directory (e.g. "backend/src/**" -> "backend/src/")
        glob_base = declared.split("*")[0].rstrip("/")
        if glob_base:
            base_path = (root / glob_base).resolve()
            if _is_relative_to(candidate, base_path):
                return True
        # Also try Path.match() (matches from the right, useful for patterns like "**/*.py")
        if Path(path_or_pattern).match(declared):
            return True
        return any(candidate == match.resolve() for match in root.glob(declared))

    declared_path = (root / declared).resolve()
    if declared.endswith("/"):
        return _is_relative_to(candidate, declared_path)
    if declared_path.exists() and declared_path.is_dir():
        return _is_relative_to(candidate, declared_path)
    return candidate == declared_path or _is_relative_to(candidate, declared_path)


def _is_under_root(path: Path, root: Path) -> bool:
    return _is_relative_to(path.resolve(), root.resolve())


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
