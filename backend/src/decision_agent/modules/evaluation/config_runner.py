from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.modules.evaluation.runner import (
    CONDITION_MAP,
    list_fixtures,
    run_benchmark_sync,
)


@dataclass(frozen=True)
class BenchmarkRunConfig:
    name: str
    conditions: list[str]
    fixtures: list[str]
    reps: int
    timeout_seconds: float
    evidence_overrides: dict[str, Any]


def load_benchmark_config(path: Path) -> BenchmarkRunConfig:
    """Load and validate a benchmark run config JSON file.

    Optional fields:
      paap_min_avg_score  (float, 0–1) — override evidence profile's min_avg_score.
                          Useful for frontier sweep experiments: run the same
                          governed conditions at different governance strictness
                          levels and plot the resulting compliance-coverage curve.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    name = str(data.get("name") or path.stem)
    conditions = _string_list(data.get("conditions"), "conditions")
    fixtures = _string_list(data.get("fixtures"), "fixtures")
    reps = int(data.get("reps", 1))
    timeout_seconds = float(data.get("timeout_seconds", 600.0))

    if reps < 1:
        raise ValueError("Benchmark config reps must be >= 1.")
    if timeout_seconds <= 0:
        raise ValueError("Benchmark config timeout_seconds must be > 0.")

    known_conditions = set(CONDITION_MAP.keys())
    unknown_conditions = [c for c in conditions if c not in known_conditions]
    if unknown_conditions:
        raise ValueError(f"Unknown benchmark conditions: {unknown_conditions}")

    known_fixtures = set(list_fixtures())
    unknown_fixtures = [f for f in fixtures if f not in known_fixtures]
    if unknown_fixtures:
        raise ValueError(f"Unknown benchmark fixtures: {unknown_fixtures}")

    evidence_overrides: dict[str, Any] = {}
    raw_paap = data.get("paap_min_avg_score")
    if raw_paap is not None:
        val = float(raw_paap)
        if not (0.0 <= val <= 1.0):
            raise ValueError("paap_min_avg_score must be between 0.0 and 1.0.")
        evidence_overrides["min_avg_score"] = val

    return BenchmarkRunConfig(
        name=name,
        conditions=conditions,
        fixtures=fixtures,
        reps=reps,
        timeout_seconds=timeout_seconds,
        evidence_overrides=evidence_overrides,
    )


def run_benchmark_config(path: Path, root: Path) -> dict[str, Any]:
    """Execute a benchmark config synchronously and return final state."""
    cfg = load_benchmark_config(path)
    benchmark_id = _benchmark_id(cfg.name)
    return run_benchmark_sync(
        conditions=cfg.conditions,
        fixtures=cfg.fixtures,
        reps=cfg.reps,
        root=root,
        timeout_seconds=cfg.timeout_seconds,
        benchmark_id=benchmark_id,
        evidence_overrides=cfg.evidence_overrides or None,
    )


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Benchmark config field '{field}' must be a non-empty list.")
    out = [str(item).strip() for item in value if str(item).strip()]
    if not out:
        raise ValueError(f"Benchmark config field '{field}' must contain at least one value.")
    return out


def _benchmark_id(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_")
    slug = slug or "configured_benchmark"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"bench_{stamp}_{slug}_{uuid4().hex[:6]}"
