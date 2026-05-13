from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from decision_agent.modules.workers.memory_tool import _execute_memory_search
from decision_agent.modules.workers.path_rules import _file_glob_pattern, _is_under_root, _within_read_paths, _within_write_paths
from decision_agent.modules.workers.sql_tool import _execute_query_sql
from decision_agent.modules.workers.test_tool import _run_tests
from decision_agent.modules.workers.tool_definitions import TOOL_DEFINITIONS

AuditEmit = Callable[..., None]

def execute_tool(
    name: str,
    params: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path,
    audit_emit: AuditEmit,
) -> str:
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
            "Fall back to archive/knowledge/procurement/markets/ for vendor and pricing data. "
            "Call list_files to discover available files, then read_file to access them."
        )

    if name == "memory_search":
        return _execute_memory_search(params, contract, project_root, audit_emit)

    if name == "query_sql":
        return _execute_query_sql(params, contract, project_root, audit_emit)

    return f"ERROR: unknown tool '{name}'"
