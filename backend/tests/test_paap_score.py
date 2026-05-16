from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from decision_agent.modules.governance.paap import (
    build_evidence_record,
    evidence_floor_met,
    evaluate_paap,
    persist_evidence_record,
)
from decision_agent.modules.governance.paap_score import (
    DEFAULT_MIN_AVG_SCORE,
    DEFAULT_MIN_INDIVIDUAL_SCORE,
    EvidenceSource,
    coerce_source,
    score_record,
    threshold_issues,
)


PROCUREMENT_PROFILE = {
    "authority_weights": {
        "signed_contract":  1.00,
        "approved_spec":    0.95,
        "compliance_rule":  0.95,
        "budget_approval":  0.90,
        "vendor_proposal":  0.70,
        "market_benchmark": 0.65,
        "reference_check":  0.60,
        "analyst_estimate": 0.40,
        "model_inference":  0.00,
    },
    "conflict_rules": [
        "Model inference may not be cited as a source.",
        "Legal and compliance constraints override cost optimisation.",
    ],
    "min_avg_score": 0.6,
    "min_individual_score": 0.4,
    "temporal_half_life_days": 365,
}

NOW = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)


class TestPureFormulaDeterminism(unittest.TestCase):
    def test_score_record_is_deterministic(self) -> None:
        sources = [
            EvidenceSource(id="s1", type="vendor_proposal", excerpt="", created_at="2026-04-01"),
            EvidenceSource(id="s2", type="compliance_rule", excerpt="", created_at="2026-04-01"),
        ]
        a = score_record(sources, PROCUREMENT_PROFILE, NOW)
        b = score_record(sources, PROCUREMENT_PROFILE, NOW)
        self.assertEqual(a.score, b.score)
        self.assertEqual(a.breakdown, b.breakdown)

    def test_empty_sources_returns_zero_score(self) -> None:
        record = score_record([], PROCUREMENT_PROFILE, NOW)
        self.assertEqual(record.score, 0.0)
        self.assertEqual(record.breakdown, {})

    def test_model_inference_scores_zero(self) -> None:
        record = score_record(
            [EvidenceSource(id="m", type="model_inference", excerpt="", created_at="2026-05-01")],
            PROCUREMENT_PROFILE,
            NOW,
        )
        self.assertEqual(record.score, 0.0)
        self.assertEqual(record.breakdown["m"]["authority"], 0.0)

    def test_temporal_decay_reduces_score(self) -> None:
        recent = score_record(
            [EvidenceSource(id="r", type="vendor_proposal", excerpt="", created_at="2026-05-01")],
            PROCUREMENT_PROFILE,
            NOW,
        )
        old = score_record(
            [EvidenceSource(id="r", type="vendor_proposal", excerpt="", created_at="2020-05-01")],
            PROCUREMENT_PROFILE,
            NOW,
        )
        self.assertGreater(recent.score, old.score)

    def test_corroboration_boosts_when_multiple_high_authority_sources(self) -> None:
        single = score_record(
            [EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01")],
            PROCUREMENT_PROFILE,
            NOW,
        )
        many = score_record(
            [
                EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01"),
                EvidenceSource(id="b", type="approved_spec", excerpt="", created_at="2026-05-01"),
                EvidenceSource(id="c", type="compliance_rule", excerpt="", created_at="2026-05-01"),
            ],
            PROCUREMENT_PROFILE,
            NOW,
        )
        self.assertGreater(many.breakdown["a"]["corroboration"], single.breakdown["a"]["corroboration"])

    def test_high_authority_recent_sources_pass_threshold(self) -> None:
        # Five corroborating high-authority recent sources; corroboration
        # with diminishing returns pushes record_score above the 0.6 threshold.
        sources = [
            EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01"),
            EvidenceSource(id="b", type="approved_spec", excerpt="", created_at="2026-05-01"),
            EvidenceSource(id="c", type="compliance_rule", excerpt="", created_at="2026-05-01"),
            EvidenceSource(id="d", type="budget_approval", excerpt="", created_at="2026-05-01"),
            EvidenceSource(id="e", type="market_benchmark", excerpt="", created_at="2026-05-01"),
        ]
        record = score_record(sources, PROCUREMENT_PROFILE, NOW)
        self.assertGreaterEqual(record.score, PROCUREMENT_PROFILE["min_avg_score"])
        self.assertEqual(threshold_issues(record, PROCUREMENT_PROFILE), [])

    def test_two_high_authority_sources_below_threshold_corroboration_too_low(self) -> None:
        # Two sources: corroboration with diminishing returns formula is low
        # → cannot clear threshold even with perfect authority.
        sources = [
            EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01"),
            EvidenceSource(id="b", type="approved_spec", excerpt="", created_at="2026-05-01"),
        ]
        record = score_record(sources, PROCUREMENT_PROFILE, NOW)
        self.assertLess(record.score, PROCUREMENT_PROFILE["min_avg_score"])

    def test_low_authority_sources_fail_threshold(self) -> None:
        sources = [
            EvidenceSource(id="a", type="analyst_estimate", excerpt="", created_at="2026-05-01"),
        ]
        record = score_record(sources, PROCUREMENT_PROFILE, NOW)
        issues = threshold_issues(record, PROCUREMENT_PROFILE)
        self.assertTrue(any("min_avg_score" in i for i in issues))


class TestCoerceSource(unittest.TestCase):
    def test_dict_with_id_preserved(self) -> None:
        s = coerce_source({"id": "x", "type": "vendor_proposal", "excerpt": "v"}, fallback_index=0)
        self.assertEqual(s.id, "x")
        self.assertEqual(s.type, "vendor_proposal")

    def test_dict_without_id_gets_synthesized(self) -> None:
        s1 = coerce_source({"type": "vendor_proposal"}, fallback_index=0)
        s2 = coerce_source({"type": "vendor_proposal"}, fallback_index=0)
        self.assertEqual(s1.id, s2.id)  # deterministic given same input

    def test_string_form_works(self) -> None:
        s = coerce_source("vendor_proposal", fallback_index=2)
        self.assertEqual(s.type, "vendor_proposal")

    def test_empty_or_invalid_returns_none(self) -> None:
        self.assertIsNone(coerce_source(None))
        self.assertIsNone(coerce_source({}))
        self.assertIsNone(coerce_source(""))


class TestEvaluatePaap(unittest.TestCase):
    def test_reject_when_record_below_threshold(self) -> None:
        contract = {
            "evidence_profile": PROCUREMENT_PROFILE,
            "worker_id": "evaluator",
            "validators": ["evidence_sources_declared"],
        }
        output = {
            "evidence_sources": [
                {"id": "s1", "type": "analyst_estimate", "created_at": "2020-01-01"},
            ],
        }
        issues, record = evaluate_paap(output, contract, project_root=None, now_utc=NOW)
        self.assertTrue(issues)
        self.assertLess(record.score, PROCUREMENT_PROFILE["min_avg_score"])

    def test_persist_evidence_when_root_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = {
                "evidence_profile": PROCUREMENT_PROFILE,
                "worker_id": "evaluator",
                "run_id": "run_abc",
                "validators": ["evidence_sources_declared"],
            }
            output = {
                "evidence_sources": [
                    {"id": "s1", "type": "signed_contract", "created_at": "2026-05-01"},
                    {"id": "s2", "type": "approved_spec", "created_at": "2026-05-01"},
                    {"id": "s3", "type": "compliance_rule", "created_at": "2026-05-01"},
                    {"id": "s4", "type": "budget_approval", "created_at": "2026-05-01"},
                    {"id": "s5", "type": "market_benchmark", "created_at": "2026-05-01"},
                ],
            }
            issues, record = evaluate_paap(output, contract, project_root=root, now_utc=NOW)
            self.assertEqual(issues, [])
            written = root / "data" / "runs" / "run_abc" / "evidence" / "evaluator.json"
            self.assertTrue(written.exists())
            data = json.loads(written.read_text("utf-8"))
            self.assertEqual(data["worker_id"], "evaluator")
            self.assertEqual(data["score"], record.score)


class TestEvidenceFloorMet(unittest.TestCase):
    def test_floor_met_after_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            sources = [
                EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01"),
                EvidenceSource(id="b", type="approved_spec", excerpt="", created_at="2026-05-01"),
                EvidenceSource(id="c", type="compliance_rule", excerpt="", created_at="2026-05-01"),
                EvidenceSource(id="d", type="budget_approval", excerpt="", created_at="2026-05-01"),
                EvidenceSource(id="e", type="market_benchmark", excerpt="", created_at="2026-05-01"),
            ]
            record = score_record(sources, PROCUREMENT_PROFILE, NOW, worker_id="evaluator")
            persist_evidence_record(record, "run_x", runs_dir)
            met, mean = evidence_floor_met("run_x", runs_dir, PROCUREMENT_PROFILE)
            self.assertTrue(met)
            self.assertGreater(mean, 0.0)

    def test_floor_unmet_when_no_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            met, mean = evidence_floor_met("nope", Path(tmp), PROCUREMENT_PROFILE)
            self.assertFalse(met)
            self.assertEqual(mean, 0.0)


STRUCTURAL_PROFILE = {
    "evidence_types": {
        "signed_contract":  {"independence": "authoritative", "default_verification_depth": 3},
        "approved_spec":    {"independence": "authoritative", "default_verification_depth": 2},
        "compliance_rule":  {"independence": "authoritative", "default_verification_depth": 2},
        "vendor_proposal":  {"independence": "self_reported",  "default_verification_depth": 1},
        "market_benchmark": {"independence": "independent",    "default_verification_depth": 1},
        "analyst_estimate": {"independence": "self_reported",  "default_verification_depth": 0},
        "model_inference":  {"independence": "",               "default_verification_depth": 0},
    },
    "conflict_rules": [],
    "min_avg_score": 0.5,
    "min_individual_score": 0.25,
    "temporal_half_life_days": 365,
}


class TestStructuralAuthority(unittest.TestCase):
    def test_authoritative_scores_higher_than_self_reported(self) -> None:
        auth = score_record(
            [EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01")],
            STRUCTURAL_PROFILE, NOW,
        )
        self_rep = score_record(
            [EvidenceSource(id="b", type="vendor_proposal", excerpt="", created_at="2026-05-01")],
            STRUCTURAL_PROFILE, NOW,
        )
        self.assertGreater(auth.score, self_rep.score)

    def test_model_inference_scores_zero_structural(self) -> None:
        record = score_record(
            [EvidenceSource(id="m", type="model_inference", excerpt="", created_at="2026-05-01")],
            STRUCTURAL_PROFILE, NOW,
        )
        self.assertAlmostEqual(record.breakdown["m"]["authority"], 0.0)

    def test_verification_depth_increases_authority(self) -> None:
        shallow = score_record(
            [EvidenceSource(id="a", type="vendor_proposal", excerpt="", created_at="2026-05-01",
                            independence="self_reported", verification_depth=0)],
            STRUCTURAL_PROFILE, NOW,
        )
        deep = score_record(
            [EvidenceSource(id="a", type="vendor_proposal", excerpt="", created_at="2026-05-01",
                            independence="self_reported", verification_depth=3)],
            STRUCTURAL_PROFILE, NOW,
        )
        self.assertGreater(deep.score, shallow.score)

    def test_source_independence_overrides_profile_default(self) -> None:
        """When source declares independence, it takes precedence over profile default."""
        # vendor_proposal defaults to self_reported in profile, but source says independent
        upgraded = score_record(
            [EvidenceSource(id="a", type="vendor_proposal", excerpt="", created_at="2026-05-01",
                            independence="independent", verification_depth=2)],
            STRUCTURAL_PROFILE, NOW,
        )
        default = score_record(
            [EvidenceSource(id="a", type="vendor_proposal", excerpt="", created_at="2026-05-01")],
            STRUCTURAL_PROFILE, NOW,
        )
        self.assertGreater(upgraded.score, default.score)

    def test_independence_ordering_is_strict(self) -> None:
        """authoritative > independent > second_party > self_reported."""
        from decision_agent.modules.governance.paap_score import INDEPENDENCE_TIERS
        tiers = list(INDEPENDENCE_TIERS.values())
        for i in range(len(tiers) - 1):
            self.assertLess(tiers[i], tiers[i + 1])

    def test_corroboration_diminishing_returns(self) -> None:
        """More sources increase score, but with diminishing returns."""
        scores = []
        for n in [1, 3, 5, 10]:
            sources = [
                EvidenceSource(id=f"s{i}", type="approved_spec", excerpt="", created_at="2026-05-01")
                for i in range(n)
            ]
            record = score_record(sources, STRUCTURAL_PROFILE, NOW)
            scores.append(record.score)
        # Each additional batch gives less marginal improvement
        gain_1_to_3 = scores[1] - scores[0]
        gain_3_to_5 = scores[2] - scores[1]
        gain_5_to_10 = scores[3] - scores[2]
        self.assertGreater(gain_1_to_3, gain_3_to_5)
        self.assertGreater(gain_3_to_5, gain_5_to_10)

    def test_structural_deterministic(self) -> None:
        sources = [
            EvidenceSource(id="a", type="signed_contract", excerpt="", created_at="2026-05-01",
                           independence="authoritative", verification_depth=3),
            EvidenceSource(id="b", type="vendor_proposal", excerpt="", created_at="2026-05-01",
                           independence="self_reported", verification_depth=1),
        ]
        a = score_record(sources, STRUCTURAL_PROFILE, NOW)
        b = score_record(sources, STRUCTURAL_PROFILE, NOW)
        self.assertEqual(a.score, b.score)
        self.assertEqual(a.breakdown, b.breakdown)

    def test_coerce_source_parses_structural_fields(self) -> None:
        raw = {
            "id": "x", "type": "vendor_proposal", "excerpt": "v",
            "independence": "self_reported", "verification_depth": 2,
        }
        s = coerce_source(raw)
        self.assertEqual(s.independence, "self_reported")
        self.assertEqual(s.verification_depth, 2)

    def test_coerce_source_defaults_structural_fields(self) -> None:
        raw = {"id": "x", "type": "vendor_proposal"}
        s = coerce_source(raw)
        self.assertEqual(s.independence, "")
        self.assertEqual(s.verification_depth, 0)


if __name__ == "__main__":
    unittest.main()
