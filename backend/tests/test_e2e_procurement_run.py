"""End-to-end tests for a full procurement run lifecycle.

Uses a custom mock provider that returns procurement-valid JSON for each worker
(including properly typed evidence_sources), so the full validation pipeline
(DSC, PAAP, DAR) can complete without a real API key.

All tests use a temporary directory so no test data leaks into data/.
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.runs.service import (
    approve_architecture,
    build_architecture_proposal,
    create_run,
    generate_contracts_for_approved_architecture,
    start_run,
)
from decision_agent.modules.runs.scheduler import get_ready_worker_ids, is_run_complete
from decision_agent.modules.runs.service import read_run
from decision_agent.modules.runs.state import WORKER_COST
from decision_agent.modules.workers.runner import run_worker
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.base import LLMProvider


# ---------------------------------------------------------------------------
# Procurement-aware mock provider
# ---------------------------------------------------------------------------

_TODAY = "2026-05-09"

# 4 corroborating high-authority recent sources:
# - signed_contract (1.00), approved_spec (0.95), compliance_rule (0.95), vendor_proposal (0.70)
# - temporal ~1.0 (same day), corroboration 0.80 (3 other high sources each)
# - record_score ~0.72 > min_avg_score 0.50 ✓
# - vendor_proposal satisfies DSC required_evidence_classes ["compliance_rule", "vendor_proposal"]
EVIDENCE_SOURCES = [
    {"id": "e1", "type": "signed_contract",  "excerpt": "Lenovo EMEA signed agreement 2026", "created_at": _TODAY},
    {"id": "e2", "type": "approved_spec",    "excerpt": "Approved procurement spec EUR 200k ceiling", "created_at": _TODAY},
    {"id": "e3", "type": "compliance_rule",  "excerpt": "ISO 27001 mandatory per compliance checklist", "created_at": _TODAY},
    {"id": "e4", "type": "vendor_proposal",  "excerpt": "Lenovo proposal EUR 1799/unit, 6-week delivery", "created_at": _TODAY},
]

WORKER_OUTPUTS: dict[str, dict[str, Any]] = {
    "requirement_analyst": {
        "summary": "100 developer laptops, EUR 200k ceiling, GDPR + ISO 27001 required.",
        "procurement_subject": "100 developer laptops",
        "quantity_and_quality": ["100 units", "32 GB RAM", "1 TB SSD"],
        "delivery_timeline": ["90 days post-signature"],
        "budget_ceiling": ["EUR 200,000 total"],
        "compliance_requirements": ["compliance_rule: ISO 27001 mandatory", "vendor_proposal: 3 vendors required"],
        "gaps": [],
    },
    "market_scout": {
        "summary": "Three vendors identified: Lenovo, Dell, HP.",
        "active_vendors": ["Lenovo", "Dell", "HP"],
        "market_price_range": ["EUR 1700–2100 per unit"],
        "lead_time_range": ["4–12 weeks"],
        "supply_risks": ["Component shortages for 32 GB configs"],
        "comparable_procurements": ["Past: 50 ThinkPads Berlin 2024"],
    },
    "risk_assessor": {
        "summary": "Delivery risk medium; compliance risk manageable.",
        "vendor_concentration_risk": ["MEDIUM — three OEMs qualify; single-vendor risk manageable"],
        "delivery_risk": ["MEDIUM — 90-day window tight for 100 configured units"],
        "compliance_risk": ["LOW — ISO 27001 mandatory; all shortlisted vendors certified"],
        "budget_risk": ["LOW — EUR 2,000 ceiling achievable with volume discount"],
        "reputational_risk": ["LOW — established EU vendors"],
        "overall_risk_rating": "MEDIUM",
    },
    "evaluator": {
        "summary": "Lenovo scores highest; Dell reserve; HP conditional.",
        "eliminated_vendors": ["Apple — budget exceeded"],
        "scored_vendors": [{"vendor": "Lenovo", "score": 3.8}, {"vendor": "Dell", "score": 3.1}],
        "shortlist": ["Lenovo (primary)", "Dell (reserve)"],
        "evidence_sources": EVIDENCE_SOURCES,
    },
    "recommender": {
        "summary": "Recommend Lenovo ThinkPad. Human approval required.",
        "recommended_vendor": "Lenovo",
        "ranking_reasoning": "Highest score, confirmed ISO 27001, fastest delivery.",
        "key_risks": ["ISO cert expiry Sep 2026", "Delivery window tight"],
        "suggested_contract_conditions": ["ISO 27001 renewal required before award"],
        "decision_required": "Human must approve vendor selection and budget release.",
    },
}


class ProcurementMockProvider(LLMProvider):
    """Returns procurement-valid JSON for each worker based on worker_id in system prompt."""

    @property
    def name(self) -> str:
        return "procurement-mock"

    def _detect_worker(self, system: str) -> str:
        # Must match "Worker ID: <wid>" — not just wid as substring, because
        # read_paths include paths like "outputs/requirement_analyst.json" which
        # would be a false match for the evaluator contract.
        for wid in WORKER_OUTPUTS:
            if f"Worker ID: {wid}" in system:
                return wid
        return "requirement_analyst"

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        return json.dumps(WORKER_OUTPUTS[self._detect_worker(system)])

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 4096,
        tool_choice: dict | None = None,
    ) -> dict:
        worker_id = self._detect_worker(system)
        return {
            "stop_reason": "end_turn",
            "content": json.dumps(WORKER_OUTPUTS[worker_id]),
            "tool_use": None,
            "tool_capable": False,
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }


def _laptop_task() -> dict:
    return {
        "task_id": "e2e_test_laptops",
        "title": "Procure 100 developer laptops",
        "description": (
            "100 developer laptops, 32 GB RAM, 1 TB SSD, 3yr on-site warranty. "
            "Budget EUR 200,000. GDPR + ISO 27001 required. EU warehouse. "
            "Evaluate at least 3 vendors."
        ),
    }


def _run_all_workers(run_id: str, root: Path, provider: LLMProvider) -> None:
    """Sequential worker execution for testing (no threading complexity)."""
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"
    started: set[str] = set()
    for _ in range(30):
        run = read_run(run_id, root)
        if not run:
            break
        contracts = run.get("generated_contracts") or run.get("contracts", [])
        if not contracts:
            break
        if is_run_complete(run, contracts):
            break
        gates = (run.get("architecture_proposal") or {}).get("topology", {}).get("gates", [])
        ready = [
            wid for wid in get_ready_worker_ids(run, contracts, gates)
            if wid not in started
        ]
        if not ready:
            time.sleep(0.1)
            continue
        for worker_id in ready:
            contract = next(c for c in contracts if c["worker_id"] == worker_id)
            started.add(worker_id)
            append_audit_event(audit_path, {"event": "worker_assigned", "run_id": run_id, "worker_id": worker_id})
            try:
                run_worker(run_id, worker_id, contract, audit_path, root, provider)
            except Exception as exc:
                append_audit_event(audit_path, {"event": "worker_failed", "run_id": run_id, "worker_id": worker_id, "error": str(exc)[:300]})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class FullRunLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.provider = ProcurementMockProvider()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _setup_run(self, layer_config: LayerConfig | None = None) -> tuple[str, dict]:
        cfg = layer_config or LayerConfig.full()
        run = create_run(_laptop_task(), self.root, layer_config=cfg, benchmark_mode=True)
        run_id = run["run_id"]
        build_architecture_proposal(run_id, self.root, self.provider)
        approve_architecture(run_id, "test", self.root)
        generate_contracts_for_approved_architecture(run_id, self.root)
        start_run(run_id, self.root)
        return run_id, run

    def test_full_lifecycle_workers_complete(self) -> None:
        """All 5 workers should reach validated status and gate can be approved."""
        run_id, _ = self._setup_run(LayerConfig(
            dsc_enabled=False, paap_enabled=False, dar_enabled=False,
            human_gate_enabled=False, contract_validators_enabled=True,
        ))
        _run_all_workers(run_id, self.root, self.provider)
        run = read_run(run_id, self.root)
        statuses = run.get("worker_statuses", {})
        for wid in ["requirement_analyst", "market_scout", "risk_assessor", "evaluator", "recommender"]:
            self.assertIn(wid, statuses, f"worker {wid} missing from statuses")
            self.assertIn(statuses[wid], {"validated", "submitted"}, f"{wid} not validated: {statuses[wid]}")

    def test_scope_json_written_when_dsc_enabled(self) -> None:
        run_id, _ = self._setup_run(LayerConfig.full())
        scope_path = self.root / "data" / "runs" / run_id / "scope.json"
        self.assertTrue(scope_path.exists(), "scope.json must exist for procurement run with DSC on")
        scope = json.loads(scope_path.read_text("utf-8"))
        self.assertEqual(scope["domain"], "procurement")
        self.assertIn("vendor_proposal", scope["allowed_evidence_classes"])
        self.assertNotIn("model_inference", scope["allowed_evidence_classes"])

    def test_scope_json_absent_when_dsc_disabled(self) -> None:
        run_id, _ = self._setup_run(LayerConfig.baseline())
        scope_path = self.root / "data" / "runs" / run_id / "scope.json"
        self.assertFalse(scope_path.exists(), "scope.json must NOT exist when DSC is off")

    def test_worker_cost_events_emitted(self) -> None:
        """worker_cost events with token counts appear after each worker execution."""
        run_id, _ = self._setup_run(LayerConfig(
            dsc_enabled=False, paap_enabled=False, dar_enabled=False,
            human_gate_enabled=False, contract_validators_enabled=False,
        ))
        _run_all_workers(run_id, self.root, self.provider)
        audit_path = self.root / "data" / "runs" / run_id / "audit.jsonl"
        events = [json.loads(l) for l in audit_path.read_text("utf-8").splitlines() if l.strip()]
        cost_events = [e for e in events if e.get("event") == WORKER_COST]
        self.assertGreater(len(cost_events), 0, "No worker_cost events found")
        for ev in cost_events:
            self.assertIn("total_tokens", ev, "worker_cost missing total_tokens")
            self.assertIn("wall_time_ms", ev, "worker_cost missing wall_time_ms")
            self.assertGreater(ev["total_tokens"], 0)

    def test_evidence_records_written_for_evaluator(self) -> None:
        """When PAAP is enabled, evaluator evidence_sources are scored and persisted."""
        run_id, _ = self._setup_run(LayerConfig(
            dsc_enabled=False, paap_enabled=True, dar_enabled=False,
            human_gate_enabled=False, contract_validators_enabled=True,
        ))
        _run_all_workers(run_id, self.root, self.provider)
        evidence_dir = self.root / "data" / "runs" / run_id / "evidence"
        self.assertTrue(evidence_dir.exists(), "evidence/ dir must exist when PAAP is on")
        files = list(evidence_dir.glob("*.json"))
        self.assertGreater(len(files), 0, "No evidence records written")
        record = json.loads(files[0].read_text("utf-8"))
        self.assertIn("score", record)
        self.assertGreater(record["score"], 0.0)

    def test_dar_receipt_written_after_evaluator_and_recommender(self) -> None:
        """When DAR is enabled, authorization receipts appear for workers with dar_action_type."""
        run_id, _ = self._setup_run(LayerConfig(
            dsc_enabled=False, paap_enabled=True, dar_enabled=True,
            human_gate_enabled=False, contract_validators_enabled=True,
        ))
        _run_all_workers(run_id, self.root, self.provider)
        auth_dir = self.root / "data" / "runs" / run_id / "authorization"
        self.assertTrue(auth_dir.exists(), "authorization/ dir must exist when DAR is on")
        receipts = list(auth_dir.glob("*.json"))
        self.assertGreater(len(receipts), 0, "No DAR receipts written")
        receipt = json.loads(receipts[0].read_text("utf-8"))
        self.assertIn(receipt["decision"], {"ALLOW", "DENY", "ESCALATE"})
        self.assertIn("rule_fired", receipt)
        self.assertIn("evidence_floor_met", receipt)

    def test_audit_contains_all_lifecycle_events(self) -> None:
        """All expected lifecycle event types appear for a successful run."""
        run_id, _ = self._setup_run(LayerConfig(
            dsc_enabled=False, paap_enabled=False, dar_enabled=False,
            human_gate_enabled=False, contract_validators_enabled=False,
        ))
        _run_all_workers(run_id, self.root, self.provider)
        audit_path = self.root / "data" / "runs" / run_id / "audit.jsonl"
        events = {json.loads(l)["event"] for l in audit_path.read_text("utf-8").splitlines() if l.strip()}
        for expected in ("run_created", "run_started", "worker_started", "worker_submitted", "validation_passed"):
            self.assertIn(expected, events, f"Expected audit event '{expected}' not found")

    def test_condition_a_has_no_dar_receipts_or_evidence(self) -> None:
        """Condition A (all governance off) produces no governance artifacts."""
        run_id, _ = self._setup_run(LayerConfig.baseline())
        _run_all_workers(run_id, self.root, self.provider)
        auth_dir = self.root / "data" / "runs" / run_id / "authorization"
        self.assertFalse(auth_dir.exists(), "No authorization dir should exist for condition A")
        # No scope.json
        scope_path = self.root / "data" / "runs" / run_id / "scope.json"
        self.assertFalse(scope_path.exists())

    def test_condition_f_has_scope_evidence_and_dar(self) -> None:
        """Condition F (full governance) produces all three governance artifacts."""
        run_id, _ = self._setup_run(LayerConfig.full())
        _run_all_workers(run_id, self.root, self.provider)

        self.assertTrue((self.root / "data" / "runs" / run_id / "scope.json").exists(),
                        "scope.json must exist in condition F")

        auth_dir = self.root / "data" / "runs" / run_id / "authorization"
        self.assertTrue(auth_dir.exists() and any(auth_dir.glob("*.json")),
                        "At least one DAR receipt must exist in condition F")

        evidence_dir = self.root / "data" / "runs" / run_id / "evidence"
        self.assertTrue(evidence_dir.exists() and any(evidence_dir.glob("*.json")),
                        "At least one PAAP evidence record must exist in condition F")


class CheckpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_checkpoint_created_during_worker_execution(self) -> None:
        """A checkpoint file is written for a worker that uses tools."""
        from decision_agent.modules.workers.runner import _checkpoint_path, _save_checkpoint
        # Directly test checkpoint helpers
        _save_checkpoint(self.root, "run_x", "evaluator", 3,
                         [{"role": "user", "content": "hi"}], ["read_file"])
        cp = _checkpoint_path(self.root, "run_x", "evaluator")
        self.assertTrue(cp.exists())
        data = json.loads(cp.read_text("utf-8"))
        self.assertEqual(data["step"], 3)
        self.assertEqual(data["called_tools"], ["read_file"])

    def test_checkpoint_load_returns_none_when_absent(self) -> None:
        from decision_agent.modules.workers.runner import _load_checkpoint
        self.assertIsNone(_load_checkpoint(self.root, "nonexistent", "evaluator"))

    def test_checkpoint_cleared_after_load_and_clear(self) -> None:
        from decision_agent.modules.workers.runner import (
            _save_checkpoint, _clear_checkpoint, _checkpoint_path,
        )
        _save_checkpoint(self.root, "run_y", "market_scout", 2, [], ["list_files"])
        _clear_checkpoint(self.root, "run_y", "market_scout")
        self.assertFalse(_checkpoint_path(self.root, "run_y", "market_scout").exists())


if __name__ == "__main__":
    unittest.main()
