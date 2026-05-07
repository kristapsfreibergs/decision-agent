import unittest

from decision_agent.modules.contracts.output_validator import validate_contractual_output


EVIDENCE_PROFILE = {
    "authority_weights": {
        "approved_spec": 0.95,
        "market_benchmark": 0.65,
        "model_inference": 0.0,
    }
}


class OutputValidatorTest(unittest.TestCase):
    def test_rejects_missing_evidence_sources(self) -> None:
        issues = validate_contractual_output(
            {"summary": "done"},
            {"validators": ["evidence_sources_declared"], "evidence_profile": EVIDENCE_PROFILE},
        )

        self.assertTrue(any("no evidence_sources" in issue for issue in issues))

    def test_rejects_blocked_string_evidence_source(self) -> None:
        issues = validate_contractual_output(
            {"evidence_sources": ["model_inference estimate"]},
            {"validators": ["evidence_sources_declared"], "evidence_profile": EVIDENCE_PROFILE},
        )

        self.assertTrue(any("blocked source type" in issue for issue in issues))

    def test_rejects_zero_weight_evidence_source(self) -> None:
        issues = validate_contractual_output(
            {"evidence_sources": [{"type": "analyst_estimate", "authority_weight": 0.0}]},
            {"validators": ["evidence_sources_declared"], "evidence_profile": EVIDENCE_PROFILE},
        )

        self.assertTrue(any("authority_weight=0" in issue for issue in issues))

    def test_accepts_declared_authoritative_evidence(self) -> None:
        issues = validate_contractual_output(
            {
                "evidence_sources": [
                    {"type": "approved_spec", "authority_weight": 0.95},
                    "market_benchmark: pricing-benchmarks.md",
                ]
            },
            {"validators": ["evidence_sources_declared"], "evidence_profile": EVIDENCE_PROFILE},
        )

        self.assertEqual(issues, [])

    def test_rejects_reported_files_changed_outside_write_scope(self) -> None:
        issues = validate_contractual_output(
            {"files_changed": ["backend/src/decision_agent/server.py"]},
            {
                "validators": ["write_scope"],
                "write_paths": ["data/runs/run_test/workspace/evaluation.md"],
            },
        )

        self.assertTrue(any("write_scope" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
