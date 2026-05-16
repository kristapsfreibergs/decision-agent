from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_DEFAULT_STAGE_LOCK = threading.Lock()
_DEFAULT_STAGES: dict[str, str] = {}


def _resolve_case_studies_dir() -> Path:
    """Resolve case_studies root from env var or by walking up to repo root."""
    env = os.environ.get("CASE_STUDIES_DIR", "").strip()
    if env:
        return Path(env)
    # Walk up from this file to find the case_studies/ directory
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "case_studies"
        if candidate.is_dir():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    # Fallback: assume repo root is parent of backend/
    return Path(__file__).resolve().parents[5] / "case_studies"


def case_studies_dir() -> Path:
    return _resolve_case_studies_dir()


def list_case_studies() -> list[str]:
    """Return case study directory names that contain a case.json."""
    root = case_studies_dir()
    if not root.exists():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and (d / "case.json").exists()
    )


def load_case(case_id: str) -> dict[str, Any]:
    """Load case.json for a case study."""
    path = case_studies_dir() / case_id / "case.json"
    if not path.exists():
        raise FileNotFoundError(f"Case study not found: {case_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_ground_truth(case_id: str) -> dict[str, Any] | None:
    """Load ground_truth.json if it exists."""
    path = case_studies_dir() / case_id / "ground_truth.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_knowledge_index(case_id: str) -> dict[str, list[str]]:
    """Load input/index.json mapping worker_id -> file paths."""
    path = case_studies_dir() / case_id / "input" / "index.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("read_paths", {})


def knowledge_dir(case_id: str) -> Path:
    """Return the input directory for a case study."""
    return case_studies_dir() / case_id / "input"


def memory_seed_dir(case_id: str) -> Path:
    """Return the memory directory for a case study."""
    return case_studies_dir() / case_id / "memory"


def run_dir(case_id: str, condition: str, rep: int) -> Path:
    """Return the deterministic run directory path."""
    return case_studies_dir() / case_id / "output" / "runs" / f"{condition}_rep{rep}"


def staged_run_dir(case_id: str, condition: str, rep: int, stage: str) -> Path:
    """Return a timestamped/staged run directory path."""
    return case_studies_dir() / case_id / "output" / "runs" / stage / f"{condition}_rep{rep}"


def results_dir(case_id: str) -> Path:
    """Return the results directory for a case study."""
    return case_studies_dir() / case_id / "output" / "results"


def make_run_id(case_id: str, condition: str, rep: int) -> str:
    """Build a stable, readable run_id."""
    return f"{case_id}:{condition}:rep{rep}"


def make_run_stage(now: datetime | None = None) -> str:
    """Build a filesystem-safe local timestamp for experiment tracking."""
    current = now or datetime.now().astimezone()
    return current.strftime("%Y%m%d_%H%M%S")


def default_run_stage(case_id: str) -> str:
    """Return the process-wide default stage for a case-study batch.

    Ad-hoc scripts often call run_case_study() from many threads without
    passing a stage. Reusing one default stage per case keeps those reps in a
    single output/runs/{stage}/ folder for the lifetime of the Python process.
    """
    with _DEFAULT_STAGE_LOCK:
        stage = _DEFAULT_STAGES.get(case_id)
        if stage is None:
            stage = make_run_stage()
            _DEFAULT_STAGES[case_id] = stage
        return stage


def input_hash(case: dict[str, Any]) -> str:
    """Deterministic hash of case input for reproducibility tracking."""
    raw = json.dumps(case, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def ensure_run_dir(case_id: str, condition: str, rep: int, force: bool = False) -> Path:
    """Create run directory. Refuses overwrite unless force=True."""
    rd = run_dir(case_id, condition, rep)
    if rd.exists() and any(rd.iterdir()):
        if not force:
            raise FileExistsError(
                f"Run directory already exists and is not empty: {rd}\n"
                f"Use force=True to overwrite."
            )
        import shutil
        shutil.rmtree(rd)
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def ensure_staged_run_dir(
    case_id: str,
    condition: str,
    rep: int,
    stage: str | None = None,
) -> tuple[Path, str]:
    """Create a staged run leaf inside a single stage folder.

    Reusing the same stage groups repeated attempts under one top-level
    runs/{stage}/ folder. If the condition/rep leaf already exists, append a
    suffix to the leaf instead of creating another top-level stage folder.
    """
    resolved_stage = stage or default_run_stage(case_id)
    stage_dir = case_studies_dir() / case_id / "output" / "runs" / resolved_stage
    leaf = f"{condition}_rep{rep}"
    resolved_leaf = leaf
    suffix = 1
    while True:
        rd = stage_dir / resolved_leaf
        if not rd.exists():
            rd.mkdir(parents=True, exist_ok=False)
            return rd, resolved_stage
        suffix += 1
        resolved_leaf = f"{leaf}_{suffix}"


def load_case_studies_config() -> dict[str, Any]:
    """Load the root config.json with default conditions, reps, etc."""
    path = case_studies_dir() / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
