from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from decision_agent.modules.runs.scheduler import get_ready_worker_ids, has_active_workers, has_blocked_workers, is_run_complete
from decision_agent.modules.runs.service import read_run
from decision_agent.modules.workers.runner import run_worker
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.registry import get_provider

def _execute_workers_in_thread(
    run_id: str,
    root: Path,
    provider_override: str | None,
    audit_path: Path,
) -> None:
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
        worker_threads = []
        for worker_id in ready:
            contract = next(c for c in contracts if c["worker_id"] == worker_id)
            started.add(worker_id)
            append_audit_event(
                audit_path,
                {"event": "worker_assigned", "run_id": run_id, "worker_id": worker_id},
            )

            is_retry_dispatch = False
            retry_attempt_num = 0
            for evt in reversed(run.get("audit", [])):
                if evt.get("event") == "worker_assigned" and evt.get("worker_id") == worker_id:
                    is_retry_dispatch = bool(evt.get("from_checkpoint"))
                    retry_attempt_num = int(evt.get("retry_attempt", 0))
                    break

            def _run(wid=worker_id, ct=contract, ir=is_retry_dispatch, ra=retry_attempt_num):
                try:
                    run_worker(run_id, wid, ct, audit_path, root, provider,
                               is_retry=ir, retry_attempt=ra)
                except Exception as exc:
                    append_audit_event(
                        audit_path,
                        {
                            "event": "worker_failed",
                            "run_id": run_id,
                            "worker_id": wid,
                            "error": str(exc)[:500],
                        },
                    )

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            worker_threads.append(t)
        for t in worker_threads:
            t.join()


def _run_plain_model(
    run_id: str,
    fixture: dict[str, Any],
    root: Path,
    provider_override: str | None,
) -> None:
    provider = get_provider(provider_override)
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"

    system = (
        "You are an expert procurement advisor. "
        "Given a procurement task, produce a vendor recommendation as a JSON object with these fields: "
        "summary (string), eliminated_vendors (array of strings), "
        "scored_vendors (array of objects with vendor and score), "
        "shortlist (array of strings), evidence_sources (array of objects with id, type, excerpt, created_at). "
        "Output only the JSON object, nothing else."
    )
    user = (
        f"Task: {fixture.get('title', '')}\n\n"
        f"{fixture.get('description', '')}"
    )
    append_audit_event(audit_path, {"event": "worker_started", "run_id": run_id, "worker_id": "recommender"})
    try:
        raw = provider.complete(system, user)
        import re as _re
        stripped = _re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=_re.IGNORECASE)
        stripped = _re.sub(r"\s*```\s*$", "", stripped.strip())
        output = json.loads(stripped)
    except Exception as exc:
        append_audit_event(audit_path, {"event": "worker_failed", "run_id": run_id, "worker_id": "recommender", "error": str(exc)[:300]})
        return

    out_dir = root / "data" / "runs" / run_id / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recommender.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_audit_event(audit_path, {"event": "validation_passed", "run_id": run_id, "worker_id": "recommender"})
    append_audit_event(audit_path, {"event": "worker_submitted", "run_id": run_id, "worker_id": "recommender"})
    append_audit_event(audit_path, {"event": "gate_approved", "run_id": run_id, "note": "plain_model_auto"})


def _apply_evidence_overrides(run_id: str, root: Path, overrides: dict[str, Any]) -> None:
    contracts_dir = root / "data" / "runs" / run_id / "generated-contracts"
    if not contracts_dir.exists():
        return
    for contract_path in contracts_dir.glob("*.json"):
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        profile = contract.get("evidence_profile")
        if not isinstance(profile, dict):
            continue
        profile.update(overrides)
        contract["evidence_profile"] = profile
        contract_path.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

