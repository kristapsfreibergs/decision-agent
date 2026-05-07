from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.evaluation.metrics import (
    audit_completeness,
    authorization_receipt_present,
    evidence_completeness,
    extract_all_metrics,
    output_quality,
    run_completed,
    scope_violations,
    unsafe_action_count,
)
from decision_agent.modules.evaluation.report import (
    aggregate,
    evaluate_thesis_claim,
    write_csv,
    write_summary,
)


def _make_run_dir(
    base: Path,
    *,
    decision_type: str = "procurement",
    audit: list[dict] | None = None,
    outputs: dict[str, dict] | None = None,
    receipts: list[dict] | None = None,
    scope: dict | None = None,
    proposal: dict | None = None,
) -> Path:
    run_dir = base / "data" / "runs" / "run_synthetic"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-record.json").write_text(
        json.dumps(
            {
                "run_id": "run_synthetic",
                "decision_type": decision_type,
                "provider_override": "anthropic",
            }
        ),
        encoding="utf-8",
    )
    if audit is not None:
        with (run_dir / "audit.jsonl").open("w", encoding="utf-8") as h:
            for event in audit:
                h.write(json.dumps(event) + "\n")
    if outputs:
        outputs_dir = run_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        for worker_id, output in outputs.items():
            (outputs_dir / f"{worker_id}.json").write_text(
                json.dumps(output, indent=2), encoding="utf-8"
            )
    if receipts:
        auth_dir = run_dir / "authorization"
        auth_dir.mkdir(parents=True, exist_ok=True)
        for i, receipt in enumerate(receipts):
            (auth_dir / f"receipt_{i}.json").write_text(
                json.dumps(receipt, indent=2), encoding="utf-8"
            )
    if scope:
        (run_dir / "scope.json").write_text(json.dumps(scope, indent=2), encoding="utf-8")
    if proposal:
        (run_dir / "architecture-proposal.json").write_text(
            json.dumps(proposal, indent=2), encoding="utf-8"
        )
    return run_dir


class TestScopeViolations(unittest.TestCase):
    def test_baseline_run_with_speculative_output_counts_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                outputs={
                    "evaluator": {
                        "summary": "Vendor B is best, in my opinion. Rumor has it they undercut.",
                        "evidence_sources": [],
                    }
                },
            )
            self.assertGreaterEqual(scope_violations(run_dir), 2)

    def test_clean_output_has_zero_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                outputs={
                    "evaluator": {
                        "summary": "Vendor A meets compliance requirements.",
                        "evidence_sources": [{"type": "vendor_proposal"}],
                    }
                },
            )
            self.assertEqual(scope_violations(run_dir), 0)


class TestEvidenceCompleteness(unittest.TestCase):
    def test_zero_when_no_evidence_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                outputs={"evaluator": {"summary": "no sources"}},
            )
            self.assertEqual(evidence_completeness(run_dir), 0.0)

    def test_high_score_when_strong_evidence_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                outputs={
                    "evaluator": {
                        "evidence_sources": [
                            {"id": "s1", "type": "signed_contract", "created_at": "2026-05-01"},
                            {"id": "s2", "type": "approved_spec", "created_at": "2026-05-01"},
                            {"id": "s3", "type": "compliance_rule", "created_at": "2026-05-01"},
                        ]
                    }
                },
            )
            self.assertGreater(evidence_completeness(run_dir), 0.6)


class TestAuthorizationMetrics(unittest.TestCase):
    def test_receipt_present_when_allow_or_escalate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                receipts=[{"decision": "ESCALATE"}],
            )
            self.assertTrue(authorization_receipt_present(run_dir))
            self.assertEqual(unsafe_action_count(run_dir), 0)

    def test_unsafe_action_counted_on_deny(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                receipts=[{"decision": "DENY"}, {"decision": "DENY"}, {"decision": "ESCALATE"}],
            )
            self.assertEqual(unsafe_action_count(run_dir), 2)


class TestAuditCompleteness(unittest.TestCase):
    def test_zero_when_audit_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp), audit=[])
            self.assertEqual(audit_completeness(run_dir), 0.0)

    def test_full_when_all_baseline_events_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                audit=[
                    {"event": "run_created"},
                    {"event": "run_started"},
                    {"event": "contract_created"},
                    {"event": "worker_started"},
                    {"event": "worker_submitted"},
                    {"event": "validation_passed"},
                    {"event": "gate_approved"},
                ],
            )
            self.assertEqual(audit_completeness(run_dir), 1.0)


class TestRunCompleted(unittest.TestCase):
    def test_completed_when_gate_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp), audit=[{"event": "gate_approved"}])
            self.assertTrue(run_completed(run_dir))

    def test_not_completed_when_only_workers_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(Path(tmp), audit=[{"event": "worker_submitted"}])
            self.assertFalse(run_completed(run_dir))


class TestOutputQuality(unittest.TestCase):
    def test_full_when_all_required_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proposal = {
                "workers": [
                    {
                        "worker_id": "evaluator",
                        "output_schema": {
                            "required": ["summary", "scored_vendors"],
                        },
                    }
                ]
            }
            run_dir = _make_run_dir(
                Path(tmp),
                proposal=proposal,
                outputs={"evaluator": {"summary": "ok", "scored_vendors": [1, 2]}},
            )
            self.assertEqual(output_quality(run_dir), 1.0)

    def test_partial_when_some_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proposal = {
                "workers": [
                    {
                        "worker_id": "evaluator",
                        "output_schema": {
                            "required": ["summary", "scored_vendors"],
                        },
                    }
                ]
            }
            run_dir = _make_run_dir(
                Path(tmp),
                proposal=proposal,
                outputs={"evaluator": {"summary": "ok"}},
            )
            self.assertEqual(output_quality(run_dir), 0.5)


class TestExtractAllMetrics(unittest.TestCase):
    def test_returns_complete_metric_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _make_run_dir(
                Path(tmp),
                audit=[{"event": "run_created", "timestamp": "2026-05-07T12:00:00Z"}],
                outputs={"evaluator": {"summary": "x", "evidence_sources": []}},
            )
            metrics = extract_all_metrics(run_dir, "F", 0, "procurement_laptops")
            self.assertEqual(metrics["condition"], "F")
            self.assertEqual(metrics["fixture"], "procurement_laptops")
            self.assertIn("scope_violations", metrics)
            self.assertIn("evidence_completeness", metrics)
            self.assertIn("authorization_receipt_present", metrics)


class TestReport(unittest.TestCase):
    def test_aggregate_means_per_condition(self) -> None:
        results = [
            {"condition": "A", "scope_violations": 3, "evidence_completeness": 0.1, "authorization_receipt_present": False, "unsafe_action_count": 0, "audit_completeness": 0.4, "output_quality": 0.5, "time_to_complete_s": 10.0, "run_completed": False},
            {"condition": "A", "scope_violations": 2, "evidence_completeness": 0.2, "authorization_receipt_present": False, "unsafe_action_count": 1, "audit_completeness": 0.4, "output_quality": 0.5, "time_to_complete_s": 12.0, "run_completed": False},
            {"condition": "F", "scope_violations": 0, "evidence_completeness": 0.8, "authorization_receipt_present": True, "unsafe_action_count": 0, "audit_completeness": 1.0, "output_quality": 0.9, "time_to_complete_s": 30.0, "run_completed": True},
            {"condition": "F", "scope_violations": 0, "evidence_completeness": 0.75, "authorization_receipt_present": True, "unsafe_action_count": 0, "audit_completeness": 1.0, "output_quality": 0.9, "time_to_complete_s": 32.0, "run_completed": True},
        ]
        agg = aggregate(results)
        self.assertEqual(agg["A"]["scope_violations"], 2.5)
        self.assertEqual(agg["F"]["scope_violations"], 0.0)

    def test_evaluate_thesis_claim_gap_holds(self) -> None:
        agg = {
            "A": {"scope_violations": 3, "evidence_completeness": 0.2, "authorization_receipt_present": 0, "unsafe_action_count": 1, "audit_completeness": 0.4},
            "F": {"scope_violations": 0, "evidence_completeness": 0.8, "authorization_receipt_present": 1, "unsafe_action_count": 0, "audit_completeness": 1.0},
            "G_qwen":  {"scope_violations": 0, "evidence_completeness": 0.78, "authorization_receipt_present": 1, "unsafe_action_count": 0, "audit_completeness": 0.95},
            "G_llama": {"scope_violations": 0, "evidence_completeness": 0.76, "authorization_receipt_present": 1, "unsafe_action_count": 0, "audit_completeness": 0.92},
        }
        check = evaluate_thesis_claim(agg)
        self.assertTrue(check["a_to_f_gap_holds"])
        self.assertTrue(check["fg_stability_holds"])
        self.assertTrue(check["claim_proven"])

    def test_evaluate_thesis_claim_unstable_fg(self) -> None:
        agg = {
            "A": {"scope_violations": 3, "evidence_completeness": 0.2, "authorization_receipt_present": 0, "unsafe_action_count": 1, "audit_completeness": 0.4},
            "F": {"scope_violations": 0, "evidence_completeness": 0.8, "authorization_receipt_present": 1, "unsafe_action_count": 0, "audit_completeness": 1.0},
            "G_qwen": {"scope_violations": 0, "evidence_completeness": 0.5, "authorization_receipt_present": 1, "unsafe_action_count": 0, "audit_completeness": 1.0},
        }
        check = evaluate_thesis_claim(agg)
        self.assertFalse(check["fg_stability_holds"])
        self.assertFalse(check["claim_proven"])

    def test_csv_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "results.csv"
            results = [
                {"condition": "F", "fixture": "x", "rep": 0, "scope_violations": 0, "evidence_completeness": 0.8, "authorization_receipt_present": True, "unsafe_action_count": 0, "audit_completeness": 1.0, "output_quality": 0.9, "time_to_complete_s": 30.0, "run_completed": True},
            ]
            write_csv(results, target)
            self.assertTrue(target.exists())
            content = target.read_text("utf-8")
            self.assertIn("scope_violations", content)
            self.assertIn("0.8", content)


if __name__ == "__main__":
    unittest.main()
