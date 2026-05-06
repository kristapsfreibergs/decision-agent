from __future__ import annotations

import os
import shlex
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
        matches = sorted(
            path.relative_to(project_root.resolve()).as_posix()
            for path in project_root.glob(pattern)
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
        return "ERROR: web_search is not implemented in the local worker tool provider yet."

    return f"ERROR: unknown tool '{name}'"


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
