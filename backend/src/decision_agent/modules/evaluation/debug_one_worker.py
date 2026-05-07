"""Run one procurement worker end-to-end with the real provider — fast iteration loop.

Usage:
    PYTHONPATH=backend/src python -m decision_agent.modules.evaluation.debug_one_worker requirement_analyst
    PYTHONPATH=backend/src python -m decision_agent.modules.evaluation.debug_one_worker evaluator

Cheap to run (one Claude call ~ $0.02-0.10). Use it to validate the prompt and
parser BEFORE launching a 10-minute full benchmark.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from decision_agent.modules.evaluation.runner import load_fixture
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.runs.service import (
    approve_architecture,
    build_architecture_proposal,
    create_run,
    generate_contracts_for_approved_architecture,
    start_run,
)
from decision_agent.modules.workers.runner import run_worker
from decision_agent.shared.providers.registry import get_provider


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    target_worker = sys.argv[1] if len(sys.argv) > 1 else "requirement_analyst"
    fixture_id = sys.argv[2] if len(sys.argv) > 2 else "procurement_laptops"
    root = Path.cwd()

    fixture = load_fixture(fixture_id)
    fixture = {**fixture, "task_id": f"debug_{target_worker}"}

    print(f"[debug] creating run for fixture={fixture_id}")
    run = create_run(
        fixture, root, layer_config=LayerConfig.full(),
        provider_override="anthropic", benchmark_mode=True,
    )
    run_id = run["run_id"]
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"
    provider = get_provider("anthropic")

    print(f"[debug] run_id={run_id} provider={provider.name}")
    print("[debug] building architecture proposal...")
    build_architecture_proposal(run_id, root, provider)
    approve_architecture(run_id, "debug", root)
    generate_contracts_for_approved_architecture(run_id, root)
    start_run(run_id, root)

    # Find the requested worker's contract
    from decision_agent.modules.runs.service import read_run
    run = read_run(run_id, root)
    contracts = run.get("generated_contracts") or run.get("contracts", [])
    contract = next((c for c in contracts if c["worker_id"] == target_worker), None)
    if not contract:
        print(f"[debug] worker {target_worker!r} not found. Available:",
              [c["worker_id"] for c in contracts])
        return 1

    # If the worker has dependencies, populate dummy outputs to satisfy read_paths
    deps = contract.get("depends_on") or []
    if deps:
        print(f"[debug] worker has {len(deps)} dep(s); writing stub outputs")
        outputs_dir = root / "data" / "runs" / run_id / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        for dep_id in deps:
            stub = {
                "summary": f"Stub output from {dep_id} for debug.",
                "evidence_sources": [
                    {"id": "stub_a", "type": "approved_spec", "excerpt": "stub", "created_at": "2026-05-01"},
                    {"id": "stub_b", "type": "compliance_rule", "excerpt": "stub", "created_at": "2026-05-01"},
                    {"id": "stub_c", "type": "vendor_proposal", "excerpt": "stub", "created_at": "2026-05-01"},
                ],
            }
            (outputs_dir / f"{dep_id}.json").write_text(json.dumps(stub, indent=2), encoding="utf-8")
        # Also write the workspace md files some workers expect
        ws = root / "data" / "runs" / run_id / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        for fname in ("requirements.md", "market_research.md", "risk_assessment.md", "evaluation.md"):
            target = ws / fname
            if not target.exists():
                target.write_text(f"# {fname}\nStub for debug run.\n", encoding="utf-8")

    print(f"[debug] running worker {target_worker!r}...")
    print()
    try:
        output = run_worker(run_id, target_worker, contract, audit_path, root, provider)
    except Exception as exc:
        print()
        print(f"[debug] FAILED: {exc}")
        return 1

    print()
    print(f"[debug] SUCCESS. output keys: {list(output.keys())}")
    print()
    print("[debug] full output:")
    print(json.dumps(output, indent=2, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
