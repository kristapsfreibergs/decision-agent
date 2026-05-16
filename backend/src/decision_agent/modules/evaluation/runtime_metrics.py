from __future__ import annotations

from datetime import datetime
from pathlib import Path

from decision_agent.modules.evaluation.metric_loaders import _list_outputs, _load_audit, _load_run_record

_MODEL_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-5": (5.0, 25.0),
}

def model_provider(run_dir: Path) -> str:
    record = _load_run_record(run_dir)
    return record.get("provider_override") or record.get("model") or "default"


def model_name(run_dir: Path) -> str:
    record = _load_run_record(run_dir)
    return str(record.get("model") or record.get("provider_override") or "")


def cost_tokens_total(run_dir: Path) -> int:
    return tokens_input(run_dir) + tokens_output(run_dir)


def tokens_input(run_dir: Path) -> int:
    audit = _load_audit(run_dir)
    total = 0
    for event in audit:
        if event.get("event") == "worker_cost":
            total += int(event.get("input_tokens", 0))
        if event.get("event") == "llm_call_usage":
            total += int(event.get("input_tokens", 0))
    return total or _sum_output_token_field(run_dir, "input_tokens")


def tokens_output(run_dir: Path) -> int:
    audit = _load_audit(run_dir)
    total = 0
    for event in audit:
        if event.get("event") == "worker_cost":
            total += int(event.get("output_tokens", 0))
        if event.get("event") == "llm_call_usage":
            total += int(event.get("output_tokens", 0))
    return total or _sum_output_token_field(run_dir, "output_tokens")


def estimated_cost_usd(run_dir: Path) -> float | None:
    price = _price_for_model(model_name(run_dir))
    if price is None:
        return None
    input_per_mtok, output_per_mtok = price
    cost = (tokens_input(run_dir) / 1_000_000) * input_per_mtok
    cost += (tokens_output(run_dir) / 1_000_000) * output_per_mtok
    return round(cost, 6)


def _sum_output_token_field(run_dir: Path, field: str) -> int:
    total = 0
    for _, output in _list_outputs(run_dir):
        try:
            total += int(output.get(field, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _price_for_model(name: str) -> tuple[float, float] | None:
    normalized = name.lower().removeprefix("anthropic/").replace("_", "-")
    for key, price in _MODEL_PRICES_PER_MTOK.items():
        if key in normalized:
            return price
    if normalized == "anthropic":
        return _MODEL_PRICES_PER_MTOK["claude-haiku-4-5"]
    return None


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
