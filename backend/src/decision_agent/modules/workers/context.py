from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_CONTEXT_FILES = 12
MAX_CONTEXT_CHARS_PER_FILE = 4_000
SKIP_PATH_PARTS = {"__pycache__", ".git", "node_modules", ".venv"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".docx"}

def _safe_relative(path: Path, root: Path) -> str | None:
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved.relative_to(root.resolve()).as_posix()


def _is_context_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    if any(part in SKIP_PATH_PARTS for part in path.parts):
        return False
    return True


def _read_context_files(contract: dict[str, Any], project_root: Path) -> dict[str, str]:
    """Read declared context paths that exist, including bounded glob expansion."""
    context: dict[str, str] = {}
    root = project_root.resolve()

    for pattern in contract.get("read_paths", []):
        if len(context) >= MAX_CONTEXT_FILES:
            break

        matches = sorted(root.glob(pattern)) if "*" in pattern else [root / pattern]
        for path in matches:
            if len(context) >= MAX_CONTEXT_FILES:
                break
            relative = _safe_relative(path, root)
            if relative is None or not _is_context_file(path):
                continue
            try:
                context[relative] = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )[:MAX_CONTEXT_CHARS_PER_FILE]
            except OSError:
                continue
    return context
