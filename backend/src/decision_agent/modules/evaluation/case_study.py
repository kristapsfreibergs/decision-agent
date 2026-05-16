from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


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
    """Load knowledge/index.json mapping worker_id -> file paths."""
    path = case_studies_dir() / case_id / "knowledge" / "index.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("read_paths", {})


def knowledge_dir(case_id: str) -> Path:
    """Return the knowledge directory for a case study."""
    return case_studies_dir() / case_id / "knowledge"


def memory_seed_dir(case_id: str) -> Path:
    """Return the memory_seed directory for a case study."""
    return case_studies_dir() / case_id / "memory_seed"


def run_dir(case_id: str, condition: str, rep: int) -> Path:
    """Return the deterministic run directory path."""
    return case_studies_dir() / case_id / "runs" / f"{condition}_rep{rep}"


def results_dir(case_id: str) -> Path:
    """Return the results directory for a case study."""
    return case_studies_dir() / case_id / "results"


def make_run_id(case_id: str, condition: str, rep: int) -> str:
    """Build a stable, readable run_id."""
    return f"{case_id}:{condition}:rep{rep}"


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


def load_case_studies_config() -> dict[str, Any]:
    """Load the root config.json with default conditions, reps, etc."""
    path = case_studies_dir() / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
