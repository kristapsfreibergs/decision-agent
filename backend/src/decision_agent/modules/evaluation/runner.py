from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.modules.evaluation.auto_approver import (
    watch_run_to_completion,
)
from decision_agent.modules.evaluation.metrics import extract_all_metrics
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.runs.scheduler import (
    get_ready_worker_ids,
    has_active_workers,
    has_blocked_workers,
    is_run_complete,
)
from decision_agent.modules.runs.service import (
    approve_architecture,
    build_architecture_proposal,
    create_run,
    generate_contracts_for_approved_architecture,
    read_run,
    start_run,
)
from decision_agent.modules.workers.runner import run_worker
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.registry import get_provider


_FULL_CONDITION_MAP: dict[str, tuple[LayerConfig, str | None]] = {
    "A":       (LayerConfig.baseline(), None),                   # default provider
    "F":       (LayerConfig.full(),     "anthropic"),
    "G_qwen":  (LayerConfig.full(),     "ollama/qwen2.5"),
    "G_llama": (LayerConfig.full(),     "ollama/llama3.1"),
}


def _active_conditions() -> dict[str, tuple[LayerConfig, str | None]]:
    """Filter CONDITION_MAP by the BENCHMARK_PROVIDERS env var, if set.

    When BENCHMARK_PROVIDERS is unset or empty: every condition is active.
    When set to a comma-separated list (e.g. "anthropic" or
    "anthropic,ollama/qwen2.5"): only conditions whose provider is None
    (= condition A, which uses the default provider) OR matches one of the
    listed providers are exposed. Conditions referencing providers you don't
    have configured are dropped — useful when Ollama isn't running.
    """
    raw = os.environ.get("BENCHMARK_PROVIDERS", "").strip()
    if not raw:
        return dict(_FULL_CONDITION_MAP)
    allowed = {p.strip().lower() for p in raw.split(",") if p.strip()}
    filtered: dict[str, tuple[LayerConfig, str | None]] = {}
    for name, (cfg, provider) in _FULL_CONDITION_MAP.items():
        if provider is None or provider.lower() in allowed:
            filtered[name] = (cfg, provider)
    return filtered or dict(_FULL_CONDITION_MAP)


# Module-level snapshot. Re-read each access via the property-like helper so
# tests can monkey-patch the env var and see the change without a reload.
class _ConditionMapView:
    def __iter__(self):
        return iter(_active_conditions())

    def __getitem__(self, key):
        return _active_conditions()[key]

    def __contains__(self, key):
        return key in _active_conditions()

    def keys(self):
        return _active_conditions().keys()

    def items(self):
        return _active_conditions().items()

    def get(self, key, default=None):
        return _active_conditions().get(key, default)


CONDITION_MAP: Any = _ConditionMapView()

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Process-wide registry of running benchmarks (for the GET endpoint).
_BENCHMARKS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def list_fixtures() -> list[str]:
    return sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Benchmark fixture not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _execute_workers_in_thread(
    run_id: str,
    root: Path,
    provider_override: str | None,
    audit_path: Path,
) -> None:
    """In-process scheduler loop. Runs workers as they become ready."""
    started: set[str] = set()
    provider = get_provider(provider_override)
    for _ in range(240):  # ~4 minutes at 1s poll
        run = read_run(run_id, root)
        if not run:
            return
        contracts = run.get("generated_contracts") or run.get("contracts", [])
        if not contracts:
            return
        if is_run_complete(run, contracts):
            return
        gates = (run.get("architecture_proposal") or {}).get("topology", {}).get("gates", [])
        ready = [
            wid for wid in get_ready_worker_ids(run, contracts, gates)
            if wid not in started
        ]
        if not ready and not has_active_workers(run, contracts) and has_blocked_workers(run, contracts):
            return
        if not ready:
            time.sleep(1.0)
            continue
        for worker_id in ready:
            contract = next(c for c in contracts if c["worker_id"] == worker_id)
            started.add(worker_id)
            append_audit_event(
                audit_path,
                {"event": "worker_assigned", "run_id": run_id, "worker_id": worker_id},
            )
            try:
                run_worker(run_id, worker_id, contract, audit_path, root, provider)
            except Exception as exc:
                append_audit_event(
                    audit_path,
                    {
                        "event": "worker_failed",
                        "run_id": run_id,
                        "worker_id": worker_id,
                        "error": str(exc)[:500],
                    },
                )


def run_one(
    fixture_id: str,
    condition: str,
    rep: int,
    root: Path,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Execute a single benchmark run end-to-end and return its metrics."""
    layer_config, provider_override = CONDITION_MAP[condition]
    fixture = load_fixture(fixture_id)
    fixture = {**fixture, "task_id": f"{fixture['task_id']}_{condition}_rep{rep}"}

    run = create_run(
        fixture,
        root,
        layer_config=layer_config,
        provider_override=provider_override,
        benchmark_mode=True,
    )
    run_id = run["run_id"]
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"
    provider = get_provider(provider_override)

    # 1. build proposal (deterministic for procurement domain — no LLM call)
    build_architecture_proposal(run_id, root, provider)
    # 2. approve architecture (auto)
    approve_architecture(run_id, "benchmark_auto", root)
    # 3. generate contracts (with LayerConfig; DSC scope embedded if enabled)
    generate_contracts_for_approved_architecture(run_id, root)
    # 4. mark run started
    start_run(run_id, root)
    # 5. execute workers
    worker_thread = threading.Thread(
        target=_execute_workers_in_thread,
        args=(run_id, root, provider_override, audit_path),
        daemon=True,
    )
    worker_thread.start()
    # 6. auto-approve phase gates + finalize when ready
    watch_run_to_completion(run_id, root, timeout_seconds=timeout_seconds)
    worker_thread.join(timeout=10.0)

    run_dir = root / "data" / "runs" / run_id
    return extract_all_metrics(run_dir, condition, rep, fixture_id)


def run_benchmark(
    conditions: list[str],
    fixtures: list[str],
    reps: int,
    root: Path,
    timeout_seconds: float = 300.0,
) -> str:
    """Kick off a benchmark in a background thread; return its benchmark_id."""
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


def _persist_progress(out_dir: Path, state: dict[str, Any]) -> None:
    (out_dir / "progress.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def get_benchmark(benchmark_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _BENCHMARKS.get(benchmark_id)


def list_benchmarks(root: Path) -> list[dict[str, Any]]:
    """In-memory benchmarks first, then any persisted on disk."""
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
