from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decision_agent.modules.governance.paap_score import (
    EvidenceRecord,
    EvidenceSource,
    coerce_source,
    score_record,
    threshold_issues,
)


def build_evidence_record(
    output: dict[str, Any],
    profile: dict[str, Any],
    worker_id: str,
    now_utc: datetime | None = None,
) -> EvidenceRecord:
    """Parse output['evidence_sources'] into a scored EvidenceRecord."""
    raw_sources = output.get("evidence_sources") or []
    sources: list[EvidenceSource] = []
    for i, raw in enumerate(raw_sources):
        coerced = coerce_source(raw, fallback_index=i)
        if coerced is not None:
            sources.append(coerced)
    when = now_utc or datetime.now(timezone.utc)
    return score_record(sources, profile, when, worker_id=worker_id)


def persist_evidence_record(
    record: EvidenceRecord,
    run_id: str,
    runs_dir: Path,
) -> Path:
    target = runs_dir / run_id / "evidence" / f"{record.worker_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def evaluate_paap(
    output: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path | None = None,
    now_utc: datetime | None = None,
) -> tuple[list[str], EvidenceRecord]:
    """Score evidence on the output, optionally persist, return issues + record.

    Caller is responsible for checking layer_config.paap_enabled before calling.
    Persistence happens iff project_root is provided and the worker actually
    declared evidence sources (no point writing empty records).
    """
    profile = contract.get("evidence_profile") or {}
    worker_id = contract.get("worker_id", "unknown")
    record = build_evidence_record(output, profile, worker_id, now_utc=now_utc)
    issues = threshold_issues(record, profile)
    if project_root is not None and record.sources:
        run_id = contract.get("run_id")
        if run_id:
            persist_evidence_record(record, run_id, project_root / "data" / "runs")
    return issues, record


def evidence_floor_met(
    run_id: str,
    runs_dir: Path,
    profile: dict[str, Any],
) -> tuple[bool, float]:
    """Check whether persisted evidence records meet the profile's min_avg_score.

    Used by DAR to compute the evidence_floor_met flag without re-running scoring.
    Returns (met, mean_score). When no evidence records exist, met=False, mean=0.
    """
    from decision_agent.modules.governance.paap_score import DEFAULT_MIN_AVG_SCORE

    evidence_dir = runs_dir / run_id / "evidence"
    if not evidence_dir.exists():
        return False, 0.0
    scores: list[float] = []
    for record_file in sorted(evidence_dir.glob("*.json")):
        try:
            data = json.loads(record_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if "score" in data:
            scores.append(float(data["score"]))
    if not scores:
        return False, 0.0
    mean = sum(scores) / len(scores)
    threshold = float(profile.get("min_avg_score") or DEFAULT_MIN_AVG_SCORE)
    return (mean >= threshold), mean
