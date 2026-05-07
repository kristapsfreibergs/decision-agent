from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.governance.dsc import (
    ScopeContract,
    check_output_against_scope,
    derive_scope_contract,
    load_scope_contract,
    persist_scope_contract,
)
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.contracts.output_validator import validate_contractual_output
from decision_agent.modules.runs.service import create_run


class TestDeriveScopeContract(unittest.TestCase):
    def test_empty_profile_yields_permissive_scope(self) -> None:
        scope = derive_scope_contract("run_x", "generic", None)
        self.assertEqual(scope.allowed_evidence_classes, ())
        self.assertEqual(scope.required_evidence_classes, ())

    def test_derive_from_procurement_profile(self) -> None:
        from decision_agent.modules.architectures.domains.procurement import (
            DOMAIN_ID,
            SCOPE_PROFILE,
        )
        scope = derive_scope_contract("run_y", DOMAIN_ID, SCOPE_PROFILE)
        self.assertIn("vendor_proposal", scope.allowed_evidence_classes)
        self.assertNotIn("model_inference", scope.allowed_evidence_classes)
        self.assertIn("compliance_rule", scope.required_evidence_classes)


class TestPersistAndLoad(unittest.TestCase):
    def test_persist_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            scope = ScopeContract(
                run_id="run_z",
                domain="procurement",
                allowed_evidence_classes=("a", "b"),
                required_evidence_classes=("a",),
                out_of_scope_markers=("rumor",),
                scope_phrase_blocklist=("i think",),
            )
            persist_scope_contract(scope, runs_dir)
            loaded = load_scope_contract("run_z", runs_dir)
            self.assertEqual(loaded, scope)


class TestCheckOutputAgainstScope(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = ScopeContract(
            run_id="r",
            domain="procurement",
            allowed_evidence_classes=("vendor_proposal", "compliance_rule", "budget_approval"),
            required_evidence_classes=("compliance_rule",),
            out_of_scope_markers=("rumor", "personal_opinion"),
            scope_phrase_blocklist=("i think", "in my opinion"),
        )

    def test_clean_output_passes(self) -> None:
        out = {
            "summary": "Vendor A meets spec.",
            "evidence_sources": [{"type": "vendor_proposal"}, {"type": "compliance_rule"}],
        }
        self.assertEqual(check_output_against_scope(out, self.scope), [])

    def test_marker_substring_blocked(self) -> None:
        out = {"summary": "rumor says vendor B is cheaper"}
        issues = check_output_against_scope(out, self.scope)
        self.assertTrue(any("rumor" in i for i in issues))

    def test_phrase_blocklist_case_insensitive(self) -> None:
        out = {"summary": "I Think vendor B is fine"}
        issues = check_output_against_scope(out, self.scope)
        self.assertTrue(any("i think" in i for i in issues))

    def test_disallowed_evidence_class_rejected(self) -> None:
        out = {"evidence_sources": [{"type": "model_inference"}]}
        issues = check_output_against_scope(out, self.scope)
        self.assertTrue(any("not in allowed_evidence_classes" in i for i in issues))

    def test_required_only_enforced_when_flag_set(self) -> None:
        out = {"evidence_sources": [{"type": "vendor_proposal"}]}
        # Flag off: missing required is fine
        self.assertEqual(check_output_against_scope(out, self.scope), [])
        # Flag on: missing required surfaces
        issues = check_output_against_scope(out, self.scope, enforce_required_evidence=True)
        self.assertTrue(any("required evidence classes missing" in i for i in issues))


class TestValidatorIntegration(unittest.TestCase):
    def test_dsc_scope_validator_routes_to_scope_check(self) -> None:
        contract = {
            "validators": ["dsc_scope"],
            "scope_contract": {
                "run_id": "r",
                "domain": "procurement",
                "allowed_evidence_classes": ["vendor_proposal"],
                "required_evidence_classes": [],
                "out_of_scope_markers": ["rumor"],
                "scope_phrase_blocklist": [],
            },
        }
        out = {"summary": "rumor about vendor B"}
        issues = validate_contractual_output(out, contract)
        self.assertTrue(any("rumor" in i for i in issues))

    def test_dsc_scope_skipped_when_not_listed(self) -> None:
        contract = {
            "validators": ["write_scope"],
            "scope_contract": {
                "run_id": "r",
                "domain": "procurement",
                "allowed_evidence_classes": [],
                "required_evidence_classes": [],
                "out_of_scope_markers": ["rumor"],
                "scope_phrase_blocklist": [],
            },
        }
        out = {"summary": "rumor about vendor B"}
        # write_scope alone — no DSC enforcement since validator isn't declared
        self.assertEqual(validate_contractual_output(out, contract), [])


class TestProcurementRunPersistsScope(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_procurement_run_writes_scope_json(self) -> None:
        run = create_run(
            {"task_id": "t1", "title": "Procure laptops", "description": "Buy 100 laptops with budget ceiling 50k EUR"},
            self.root,
        )
        scope_path = self.root / "data" / "runs" / run["run_id"] / "scope.json"
        self.assertTrue(scope_path.exists(), "scope.json must be written for procurement runs")
        scope_data = json.loads(scope_path.read_text("utf-8"))
        self.assertEqual(scope_data["domain"], "procurement")
        self.assertIn("vendor_proposal", scope_data["allowed_evidence_classes"])

    def test_baseline_run_skips_scope_persistence(self) -> None:
        run = create_run(
            {"task_id": "t1", "title": "Procure laptops", "description": "Buy 100 laptops"},
            self.root,
            layer_config=LayerConfig.baseline(),
        )
        scope_path = self.root / "data" / "runs" / run["run_id"] / "scope.json"
        self.assertFalse(scope_path.exists(), "DSC must be skipped when layer is OFF")


if __name__ == "__main__":
    unittest.main()
