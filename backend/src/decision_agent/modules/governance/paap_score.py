from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_HALF_LIFE_DAYS = 365.0
DEFAULT_MIN_AVG_SCORE = 0.6
DEFAULT_MIN_INDIVIDUAL_SCORE = 0.4
HIGH_AUTHORITY_THRESHOLD = 0.6
CONFLICT_PENALTY_PER_RULE = 0.25
CORROBORATION_BONUS_PER_SOURCE = 0.1
CORROBORATION_BASE = 0.5


@dataclass(frozen=True)
class EvidenceSource:
    id: str
    type: str
    excerpt: str = ""
    created_at: str | None = None


@dataclass(frozen=True)
class EvidenceRecord:
    worker_id: str
    sources: tuple[EvidenceSource, ...]
    score: float
    breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    profile_thresholds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "sources": [
                {"id": s.id, "type": s.type, "excerpt": s.excerpt, "created_at": s.created_at}
                for s in self.sources
            ],
            "score": self.score,
            "breakdown": self.breakdown,
            "profile_thresholds": self.profile_thresholds,
        }


def _temporal_factor(created_at: str | None, now_utc: datetime, half_life_days: float) -> float:
    """0.5 ** (age / half_life). Missing date => 0.5 default (one half-life equivalent)."""
    if not created_at:
        return 0.5
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now_utc - created).total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 0.5
    return 0.5 ** (age_days / max(half_life_days, 1.0))


def _conflict_factor(source_type: str, conflict_rules: list[Any]) -> float:
    """1.0 - 0.25 per conflict rule whose text mentions this source type."""
    if not source_type:
        return 1.0
    needle = source_type.lower()
    triggered = sum(
        1
        for rule in conflict_rules
        if isinstance(rule, str) and needle in rule.lower()
    )
    return max(0.0, 1.0 - CONFLICT_PENALTY_PER_RULE * triggered)


def _corroboration_factor(this_authority: float, others_high_count: int) -> float:
    """0.5 base + 0.1 per other source with authority >= 0.6, capped at 1.0."""
    return min(1.0, CORROBORATION_BASE + CORROBORATION_BONUS_PER_SOURCE * others_high_count)


def score_record(
    sources: list[EvidenceSource] | tuple[EvidenceSource, ...],
    profile: dict[str, Any],
    now_utc: datetime,
    worker_id: str = "",
) -> EvidenceRecord:
    """Pure deterministic scoring. Same inputs always produce the same record."""
    weights: dict[str, float] = profile.get("authority_weights") or {}
    half_life = float(profile.get("temporal_half_life_days") or DEFAULT_HALF_LIFE_DAYS)
    conflict_rules = profile.get("conflict_rules") or []
    min_avg = float(profile.get("min_avg_score") or DEFAULT_MIN_AVG_SCORE)
    min_ind = float(profile.get("min_individual_score") or DEFAULT_MIN_INDIVIDUAL_SCORE)

    sources = tuple(sources)
    if not sources:
        return EvidenceRecord(
            worker_id=worker_id,
            sources=(),
            score=0.0,
            breakdown={},
            profile_thresholds={"min_avg_score": min_avg, "min_individual_score": min_ind},
        )

    n_high_total = sum(
        1 for s in sources if float(weights.get(s.type, 0.0)) >= HIGH_AUTHORITY_THRESHOLD
    )

    breakdown: dict[str, dict[str, float]] = {}
    source_scores: list[float] = []
    for source in sources:
        authority = float(weights.get(source.type, 0.0))
        temporal = _temporal_factor(source.created_at, now_utc, half_life)
        conflict = _conflict_factor(source.type, conflict_rules)
        others_high = max(0, n_high_total - (1 if authority >= HIGH_AUTHORITY_THRESHOLD else 0))
        corroboration = _corroboration_factor(authority, others_high)
        source_score = authority * temporal * conflict * corroboration
        breakdown[source.id] = {
            "authority": authority,
            "temporal": temporal,
            "conflict": conflict,
            "corroboration": corroboration,
            "source_score": source_score,
        }
        source_scores.append(source_score)

    record_score = sum(source_scores) / len(source_scores) if source_scores else 0.0
    return EvidenceRecord(
        worker_id=worker_id,
        sources=sources,
        score=record_score,
        breakdown=breakdown,
        profile_thresholds={"min_avg_score": min_avg, "min_individual_score": min_ind},
    )


def threshold_issues(record: EvidenceRecord, profile: dict[str, Any]) -> list[str]:
    """Return human-readable issues if any threshold is violated.

    Threshold enforcement is opt-in per evidence profile: a profile that
    omits both min_avg_score and min_individual_score is treated as
    "presence-only" — PAAP scores the record but does not reject. Domains
    that want strict scoring must declare the thresholds explicitly.
    """
    if not record.sources:
        return []
    has_thresholds = (
        "min_avg_score" in profile or "min_individual_score" in profile
    )
    if not has_thresholds:
        return []
    min_avg = float(profile.get("min_avg_score", DEFAULT_MIN_AVG_SCORE))
    min_ind = float(profile.get("min_individual_score", DEFAULT_MIN_INDIVIDUAL_SCORE))
    issues: list[str] = []
    if record.score < min_avg:
        issues.append(
            f"paap: record_score {record.score:.3f} below min_avg_score {min_avg}."
        )
    for source_id, bd in record.breakdown.items():
        if bd["source_score"] < min_ind:
            issues.append(
                f"paap: source '{source_id}' score {bd['source_score']:.3f} below "
                f"min_individual_score {min_ind}."
            )
    return issues


def coerce_source(raw: Any, fallback_index: int = 0) -> EvidenceSource | None:
    """Convert a raw evidence_sources[] entry (dict or string) into EvidenceSource."""
    if isinstance(raw, dict):
        type_value = str(raw.get("type", "")).strip()
        if not type_value:
            return None
        identifier = raw.get("id")
        if not identifier:
            seed = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
            identifier = f"src_{fallback_index}_{abs(hash(seed)) % 100000}"
        return EvidenceSource(
            id=str(identifier),
            type=type_value,
            excerpt=str(raw.get("excerpt", "")),
            created_at=raw.get("created_at"),
        )
    if isinstance(raw, str):
        type_value = raw.strip()
        if not type_value:
            return None
        return EvidenceSource(
            id=f"src_{fallback_index}_{type_value}",
            type=type_value,
            excerpt="",
            created_at=None,
        )
    return None
