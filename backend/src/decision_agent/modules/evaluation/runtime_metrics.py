from __future__ import annotations

from datetime import datetime
from pathlib import Path

from decision_agent.modules.evaluation.metric_loaders import _load_audit, _load_run_record

def model_provider(run_dir: Path) -> str:
    record = _load_run_record(run_dir)
    return record.get("provider_override") or "default"


def cost_tokens_total(run_dir: Path) -> int:
    audit = _load_audit(run_dir)
    total = 0
    for event in audit:
        if event.get("event") == "worker_cost":
            total += int(event.get("total_tokens", 0))
    return total


def worker_latency_p50_ms(run_dir: Path) -> float | None:
    audit = _load_audit(run_dir)
    times = [
        int(e["wall_time_ms"])
        for e in audit
        if e.get("event") == "worker_cost" and "wall_time_ms" in e
    ]
    if not times:
        return None
    times.sort()
    mid = len(times) // 2
    if len(times) % 2 == 0:
        return round((times[mid - 1] + times[mid]) / 2.0, 1)
    return float(times[mid])


def time_to_complete(run_dir: Path) -> float | None:
    audit = _load_audit(run_dir)
    start = next((e for e in audit if e.get("event") == "run_created"), None)
    end = next(
        (
            e
            for e in audit
            if e.get("event") in {"gate_approved", "run_completed"}
        ),
        None,
    )
    if not start or not end:
        return None
    try:
        t0 = datetime.fromisoformat(start["timestamp"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(end["timestamp"].replace("Z", "+00:00"))
        return round((t1 - t0).total_seconds(), 3)
    except (KeyError, ValueError):
        return None
