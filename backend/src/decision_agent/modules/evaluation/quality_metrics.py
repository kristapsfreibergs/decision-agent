from __future__ import annotations

from pathlib import Path

from decision_agent.modules.evaluation.metric_loaders import _list_outputs, _load_audit, _load_evidence_profile, _load_proposal

def output_quality(run_dir: Path) -> float:
    proposal = _load_proposal(run_dir)
    workers = (proposal or {}).get("workers", []) or []
    schema_by_worker = {
        w.get("worker_id"): (w.get("output_schema") or {}).get("required") or []
        for w in workers
    }
    outputs = _list_outputs(run_dir)
    if not outputs:
        return 0.0
    total_required = 0
    total_present = 0
    for worker_id, output in outputs:
        required = schema_by_worker.get(worker_id) or []
        if not required:
            continue
        total_required += len(required)
        for field in required:
            if field in output and output[field] not in (None, "", []):
                total_present += 1
    if total_required == 0:
        return 0.0
    return round(total_present / total_required, 4)


def run_completed(run_dir: Path) -> bool:
    audit = _load_audit(run_dir)
    return any(e.get("event") in {"gate_approved", "run_completed"} for e in audit)


def evidence_types_unrecognized(run_dir: Path) -> int:
    profile = _load_evidence_profile(run_dir)
    known_types = set((profile.get("authority_weights") or {}).keys())
    if not known_types:
        return 0
    count = 0
    for _, output in _list_outputs(run_dir):
        sources = output.get("evidence_sources") or []
        for source in sources:
            if isinstance(source, dict):
                src_type = str(source.get("type", "")).strip()
            elif isinstance(source, str):
                src_type = source.strip()
            else:
                continue
            if src_type and src_type not in known_types:
                count += 1
    return count


def recommendation_traceable(run_dir: Path) -> bool:
    profile = _load_evidence_profile(run_dir)
    weights: dict[str, float] = profile.get("authority_weights") or {}
    if not weights:
        return False
    for worker_id, output in _list_outputs(run_dir):
        if worker_id != "recommender":
            continue
        sources = output.get("evidence_sources") or []
        for source in sources:
            if isinstance(source, dict):
                src_type = str(source.get("type", "")).strip()
            elif isinstance(source, str):
                src_type = source.strip()
            else:
                continue
            if weights.get(src_type, 0.0) >= 0.6:
                return True
    return False
