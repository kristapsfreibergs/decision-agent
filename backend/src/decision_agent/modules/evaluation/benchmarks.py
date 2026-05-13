from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.modules.evaluation.single_run import run_one

_BENCHMARKS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

def run_benchmark(
    conditions: list[str],
    fixtures: list[str],
    reps: int,
    root: Path,
    timeout_seconds: float = 600.0,
) -> str:
    benchmark_id = (
        f"bench_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"
    )
    out_dir = root / "data" / "benchmarks" / benchmark_id
    out_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "benchmark_id": benchmark_id,
        "conditions": conditions,
        "fixtures": fixtures,
        "reps": reps,
        "started_at": datetime.now(timezone.utc).isoformat() + "Z",
        "status": "running",
        "completed_runs": 0,
        "total_runs": len(conditions) * len(fixtures) * reps,
        "results": [],
        "errors": [],
    }
    with _LOCK:
        _BENCHMARKS[benchmark_id] = state

    def _execute() -> None:
        try:
            for fixture in fixtures:
                for condition in conditions:
                    for rep in range(reps):
                        try:
                            metrics = run_one(
                                fixture, condition, rep, root, timeout_seconds
                            )
                        except Exception as exc:
                            state["errors"].append(
                                {
                                    "fixture": fixture,
                                    "condition": condition,
                                    "rep": rep,
                                    "error": str(exc)[:500],
                                }
                            )
                            metrics = {
                                "condition": condition,
                                "fixture": fixture,
                                "rep": rep,
                                "error": str(exc)[:500],
                            }
                        state["results"].append(metrics)
                        state["completed_runs"] += 1
                        _persist_progress(out_dir, state)
            state["status"] = "completed"
        except Exception as exc:
            state["status"] = "failed"
            state["errors"].append({"top_level": str(exc)[:500]})
        finally:
            state["finished_at"] = datetime.now(timezone.utc).isoformat() + "Z"
            _persist_progress(out_dir, state)
            from decision_agent.modules.evaluation.report import (
                write_csv,
                write_summary,
            )
            write_csv(state["results"], out_dir / "results.csv")
            write_summary(state, out_dir / "summary.json")

    threading.Thread(target=_execute, daemon=True).start()
    return benchmark_id


def run_benchmark_sync(
    conditions: list[str],
    fixtures: list[str],
    reps: int,
    root: Path,
    timeout_seconds: float = 600.0,
    benchmark_id: str | None = None,
    evidence_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_id = benchmark_id or (
        f"bench_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"
    )
    out_dir = root / "data" / "benchmarks" / resolved_id
    out_dir.mkdir(parents=True, exist_ok=True)

    state: dict[str, Any] = {
        "benchmark_id": resolved_id,
        "conditions": conditions,
        "fixtures": fixtures,
        "reps": reps,
        "started_at": datetime.now(timezone.utc).isoformat() + "Z",
        "status": "running",
        "completed_runs": 0,
        "total_runs": len(conditions) * len(fixtures) * reps,
        "results": [],
        "errors": [],
    }
    _persist_progress(out_dir, state)

    try:
        for fixture in fixtures:
            for condition in conditions:
                for rep in range(reps):
                    try:
                        metrics = run_one(
                            fixture, condition, rep, root, timeout_seconds,
                            evidence_overrides=evidence_overrides,
                        )
                    except Exception as exc:
                        state["errors"].append(
                            {
                                "fixture": fixture,
                                "condition": condition,
                                "rep": rep,
                                "error": str(exc)[:500],
                            }
                        )
                        metrics = {
                            "condition": condition,
                            "fixture": fixture,
                            "rep": rep,
                            "error": str(exc)[:500],
                        }
                    state["results"].append(metrics)
                    state["completed_runs"] += 1
                    _persist_progress(out_dir, state)
        state["status"] = "completed"
    except Exception as exc:
        state["status"] = "failed"
        state["errors"].append({"top_level": str(exc)[:500]})
    finally:
        state["finished_at"] = datetime.now(timezone.utc).isoformat() + "Z"
        _persist_progress(out_dir, state)
        from decision_agent.modules.evaluation.report import write_csv, write_summary
        write_csv(state["results"], out_dir / "results.csv")
        write_summary(state, out_dir / "summary.json")

    return state


def _persist_progress(out_dir: Path, state: dict[str, Any]) -> None:
    (out_dir / "progress.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def get_benchmark(benchmark_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _BENCHMARKS.get(benchmark_id)


def list_benchmarks(root: Path) -> list[dict[str, Any]]:
    with _LOCK:
        in_memory = list(_BENCHMARKS.values())
    in_memory_ids = {b["benchmark_id"] for b in in_memory}

    on_disk: list[dict[str, Any]] = []
    benchmarks_dir = root / "data" / "benchmarks"
    if benchmarks_dir.exists():
        for entry in sorted(benchmarks_dir.iterdir(), reverse=True):
            if not entry.is_dir() or entry.name in in_memory_ids:
                continue
            progress_path = entry / "progress.json"
            if not progress_path.exists():
                continue
            try:
                on_disk.append(json.loads(progress_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return in_memory + on_disk
