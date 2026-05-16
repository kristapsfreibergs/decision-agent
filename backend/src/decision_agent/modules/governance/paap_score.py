from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_HALF_LIFE_DAYS = 365.0
DEFAULT_MIN_AVG_SCORE = 0.6
DEFAULT_MIN_INDIVIDUAL_SCORE = 0.4
HIGH_AUTHORITY_THRESHOLD = 0.6
CONFLICT_PENALTY_PER_RULE = 0.25
CORROBORATION_SATURATION = 0.4

# ---------------------------------------------------------------------------
# Source independence tiers — epistemically ordered.
# The ordering is unambiguous: authoritative > independent > second_party >
# self_reported.  The specific values are a justified calibration; see thesis
# Section 7.3 for discussion.
# ---------------------------------------------------------------------------
INDEPENDENCE_TIERS: dict[str, float] = {
    "self_reported": 0.30,
    "second_party": 0.55,
    "independent": 0.80,
    "authoritative": 1.00,
}

# Verification depth bonus: each verified link in the trust chain adds 0.15.
# depth 0 = bare claim, 1 = document seen, 2 = source validated, 3 = chain complete.
VERIFICATION_BONUS_PER_DEPTH = 0.15
MAX_VERIFICATION_DEPTH = 3


@dataclass(frozen=True)
class EvidenceSource:
    id: str
    type: str
    excerpt: str = ""
    created_at: str | None = None
    independence: str = ""
    verification_depth: int = 0


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


def _corroboration_factor(corroboration_count: int) -> float:
    """Diminishing returns: 1 - e^(-0.4 * count). 0 sources → 0.0, 1 → 0.33, 3 → 0.70, 5 → 0.86."""
    if corroboration_count <= 0:
        return 0.0
    return 1.0 - math.exp(-CORROBORATION_SATURATION * corroboration_count)


def _structural_authority(source: EvidenceSource, evidence_types: dict[str, dict[str, Any]]) -> float:
    """Compute authority from structural properties instead of hardcoded weights.

    authority = independence_score × (1 + VERIFICATION_BONUS × depth)

    Independence and verification_depth come from:
    1. The source itself (if the LLM extracted them)
    2. The evidence_types declaration in the profile (fallback)
    """
    # Resolve independence tier
    independence = source.independence
    if not independence and source.type in evidence_types:
        independence = evidence_types[source.type].get("independence", "")
    independence_score = INDEPENDENCE_TIERS.get(independence, 0.0)

    # Resolve verification depth
    depth = source.verification_depth
    if depth == 0 and source.type in evidence_types:
        depth = int(evidence_types[source.type].get("default_verification_depth", 0))
    depth = min(depth, MAX_VERIFICATION_DEPTH)

    verification_bonus = 1.0 + VERIFICATION_BONUS_PER_DEPTH * depth
    return independence_score * verification_bonus


def score_record(
    sources: list[EvidenceSource] | tuple[EvidenceSource, ...],
    profile: dict[str, Any],
    now_utc: datetime,
    worker_id: str = "",
) -> EvidenceRecord:
    """Pure deterministic scoring. Same inputs always produce the same record.

    Authority is computed from structural properties (independence tier,
    verification depth, corroboration count) when ``evidence_types`` is
    declared in the profile.  Falls back to legacy ``authority_weights``
    lookup for backward compatibility.
    """
    legacy_weights: dict[str, float] = profile.get("authority_weights") or {}
    evidence_types: dict[str, dict[str, Any]] = profile.get("evidence_types") or {}
    use_structural = bool(evidence_types)

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

    # Compute authority for each source
    authorities: dict[str, float] = {}
    for source in sources:
        if use_structural:
            authorities[source.id] = _structural_authority(source, evidence_types)
        else:
            authorities[source.id] = float(legacy_weights.get(source.type, 0.0))

    # Count corroborating sources (other sources with authority >= threshold)
    n_high_total = sum(1 for a in authorities.values() if a >= HIGH_AUTHORITY_THRESHOLD)

    breakdown: dict[str, dict[str, float]] = {}
    source_scores: list[float] = []
    for source in sources:
        authority = authorities[source.id]
        temporal = _temporal_factor(source.created_at, now_utc, half_life)
        conflict = _conflict_factor(source.type, conflict_rules)
        others_high = max(0, n_high_total - (1 if authority >= HIGH_AUTHORITY_THRESHOLD else 0))
        corroboration = _corroboration_factor(others_high)
        source_score = authority * temporal * conflict * max(corroboration, 0.01)
        breakdown[source.id] = {
            "authority": round(authority, 4),
            "temporal": round(temporal, 4),
            "conflict": round(conflict, 4),
            "corroboration": round(corroboration, 4),
            "source_score": round(source_score, 4),
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
        if round(bd["source_score"], 9) < min_ind:
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
        independence = str(raw.get("independence", "")).strip()
        try:
            verification_depth = int(raw.get("verification_depth", 0))
        except (TypeError, ValueError):
            verification_depth = 0
        return EvidenceSource(
            id=str(identifier),
            type=type_value,
            excerpt=str(raw.get("excerpt", "")),
            created_at=raw.get("created_at"),
            independence=independence,
            verification_depth=verification_depth,
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
