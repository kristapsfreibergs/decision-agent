from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.governance.dar import (
    ActionProposal,
    AuthorizationReceipt,
    _decide,
    build_proposal_from_output,
    evaluate_action,
    persist_receipt,
)
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.governance.paap import persist_evidence_record
from decision_agent.modules.governance.paap_score import EvidenceSource, score_record


PROFILE = {
    "authority_weights": {
        "signed_contract": 1.0,
        "approved_spec": 0.95,
        "compliance_rule": 0.95,
        "vendor_proposal": 0.7,
    },
    "min_avg_score": 0.6,
    "min_individual_score": 0.4,
    "temporal_half_life_days": 365,
    "conflict_rules": [],
}


class TestDecisionMatrix(unittest.TestCase):
    def test_irreversible_with_human_gate_escalates(self) -> None:
        decision, rule = _decide("IRREVERSIBLE", True, LayerConfig.full())
        self.assertEqual(decision, "ESCALATE")
        self.assertIn("irreversible", rule)

    def test_irreversible_without_human_gate_denies(self) -> None:
        cfg = LayerConfig(human_gate_enabled=False)
        decision, _ = _decide("IRREVERSIBLE", True, cfg)
        self.assertEqual(decision, "DENY")

    def test_external_visible_with_evidence_escalates(self) -> None:
        decision, _ = _decide("EXTERNAL_VISIBLE", True, LayerConfig.full())
        self.assertEqual(decision, "ESCALATE")

    def test_external_visible_without_evidence_denies(self) -> None:
        decision, _ = _decide("EXTERNAL_VISIBLE", False, LayerConfig.full())
        self.assertEqual(decision, "DENY")

    def test_internal_with_evidence_allows(self) -> None:
        decision, _ = _decide("INTERNAL_REVERSIBLE", True, LayerConfig.full())
        self.assertEqual(decision, "ALLOW")

    def test_internal_without_evidence_denies(self) -> None:
        decision, _ = _decide("INTERNAL_REVERSIBLE", False, LayerConfig.full())
        self.assertEqual(decision, "DENY")

    def test_unknown_consequence_denies(self) -> None:
        decision, _ = _decide("MYSTERY_CLASS", True, LayerConfig.full())
        self.assertEqual(decision, "DENY")


class TestBuildProposal(unittest.TestCase):
    def test_returns_none_without_action_type(self) -> None:
        contract = {"run_id": "r", "worker_id": "w"}
        self.assertIsNone(build_proposal_from_output({}, contract))

    def test_collects_evidence_ids_from_dict_sources(self) -> None:
        contract = {
            "run_id": "r",
            "worker_id": "recommender",
            "dar_action_type": "publish_recommendation",
        }
        out = {
            "recommended_vendor": "VendorX",
            "evidence_sources": [
                {"id": "s1", "type": "vendor_proposal"},
                {"id": "s2", "type": "compliance_rule"},
            ],
        }
        proposal = build_proposal_from_output(out, contract)
        self.assertEqual(proposal.action_type, "publish_recommendation")
        self.assertEqual(proposal.target, "VendorX")
        self.assertEqual(set(proposal.claimed_evidence_ids), {"s1", "s2"})


class TestEvaluateAction(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.run_id = "run_dar_test"
        # Persist three high-authority sources so floor is met
        sources = [
            EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01"),
            EvidenceSource(id="b", type="approved_spec", excerpt="", created_at="2026-05-01"),
            EvidenceSource(id="c", type="compliance_rule", excerpt="", created_at="2026-05-01"),
        ]
        from datetime import datetime, timezone
        record = score_record(sources, PROFILE, datetime(2026, 5, 7, tzinfo=timezone.utc), worker_id="evaluator")
        persist_evidence_record(record, self.run_id, self.root / "data" / "runs")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_external_visible_action_escalates_when_floor_met(self) -> None:
        contract = {
            "run_id": self.run_id,
            "worker_id": "recommender",
            "dar_action_type": "publish_recommendation",
            "dar_consequence_class": "EXTERNAL_VISIBLE",
            "evidence_profile": PROFILE,
            "layer_config": LayerConfig.full().to_dict(),
        }
        proposal = ActionProposal(
            run_id=self.run_id,
            worker_id="recommender",
            action_type="publish_recommendation",
            target="VendorX",
            claimed_evidence_ids=("a", "b", "c"),
            proposed_at="2026-05-07T12:00:00Z",
        )
        receipt = evaluate_action(proposal, contract, self.root)
        self.assertEqual(receipt.decision, "ESCALATE")
        self.assertTrue(receipt.evidence_floor_met)

    def test_irreversible_action_denies_when_human_gate_off(self) -> None:
        contract = {
            "run_id": self.run_id,
            "worker_id": "recommender",
            "dar_action_type": "commit_spend",
            "dar_consequence_class": "IRREVERSIBLE",
            "evidence_profile": PROFILE,
            "layer_config": LayerConfig(
                dsc_enabled=True, paap_enabled=True, dar_enabled=True,
                human_gate_enabled=False, contract_validators_enabled=True,
            ).to_dict(),
        }
        proposal = ActionProposal(
            run_id=self.run_id,
            worker_id="recommender",
            action_type="commit_spend",
            target="VendorX",
            claimed_evidence_ids=("a",),
            proposed_at="2026-05-07T12:00:00Z",
        )
        receipt = evaluate_action(proposal, contract, self.root)
        self.assertEqual(receipt.decision, "DENY")


class TestPersistReceipt(unittest.TestCase):
    def test_receipt_round_trips_through_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            proposal = ActionProposal(
                run_id="r1",
                worker_id="w1",
                action_type="produce_brief",
                target="t",
                claimed_evidence_ids=("s1",),
                proposed_at="2026-05-07T12:00:00Z",
            )
            receipt = AuthorizationReceipt(
                receipt_id="receipt_abc",
                proposal=proposal,
                consequence_class="INTERNAL_REVERSIBLE",
                decision="ALLOW",
                rule_fired="internal_with_sufficient_evidence",
                evidence_floor_met=True,
                evidence_score=0.7,
                decided_at="2026-05-07T12:00:01Z",
            )
            persist_receipt(receipt, "r1", runs_dir)
            target = runs_dir / "r1" / "authorization" / "receipt_abc.json"
            self.assertTrue(target.exists())
            data = json.loads(target.read_text("utf-8"))
            self.assertEqual(data["decision"], "ALLOW")
            self.assertEqual(data["proposal"]["action_type"], "produce_brief")


if __name__ == "__main__":
    unittest.main()
