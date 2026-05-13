from __future__ import annotations

from pathlib import Path

def _file_glob_pattern(pattern: str) -> str:
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
        glob_base = declared.split("*")[0].rstrip("/")
        if glob_base:
            base_path = (root / glob_base).resolve()
            if _is_relative_to(candidate, base_path):
                return True
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
