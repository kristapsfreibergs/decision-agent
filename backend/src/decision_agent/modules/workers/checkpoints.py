from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def _checkpoint_path(project_root: Path, run_id: str, worker_id: str) -> Path:
    return project_root / "data" / "runs" / run_id / "checkpoints" / f"{worker_id}.json"


def _save_checkpoint(
    project_root: Path, run_id: str, worker_id: str,
    step: int, messages: list[dict[str, Any]], called_tools: list[str],
) -> None:
    cp = _checkpoint_path(project_root, run_id, worker_id)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(
        json.dumps(
            {"step": step, "messages": messages, "called_tools": called_tools},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _load_checkpoint(
    project_root: Path, run_id: str, worker_id: str,
) -> dict[str, Any] | None:
    cp = _checkpoint_path(project_root, run_id, worker_id)
    if not cp.exists():
        return None
    try:
        return json.loads(cp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _clear_checkpoint(project_root: Path, run_id: str, worker_id: str) -> None:
    _checkpoint_path(project_root, run_id, worker_id).unlink(missing_ok=True)
