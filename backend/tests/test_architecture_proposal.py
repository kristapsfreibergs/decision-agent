import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.architectures.proposal import (
    build_mock_proposal,
    validate_architecture_proposal,
)
from decision_agent.modules.runs.service import (
    approve_architecture,
    build_architecture_proposal,
    create_run,
    generate_contracts_for_approved_architecture,
    reject_architecture,
)
from decision_agent.shared.providers.mock import MockProvider


TASK = {
    "task_id": "dynamic-builder-test",
    "title": "Build dynamic architecture builder",
    "description": "Implement a bounded architecture proposal pipeline.",
    "desired_outputs": ["architecture proposal", "approval gate"],
}


class ArchitectureProposalTest(unittest.TestCase):
    def test_valid_dynamic_proposal_passes_validation(self) -> None:
        run = {
            "run_id": "run_test",
            "decision_type": "software_project_build_task",
            "risk_level": "medium",
        }
        result = validate_architecture_proposal(build_mock_proposal(run))
        self.assertTrue(result["valid"], result["issues"])

    def test_rejects_unsafe_write_scope(self) -> None:
        run = {
            "run_id": "run_test",
            "decision_type": "software_project_build_task",
            "risk_level": "medium",
        }
        proposal = build_mock_proposal(run)
        proposal["workers"][0]["write_paths"] = ["**/*"]

        result = validate_architecture_proposal(proposal)

        self.assertFalse(result["valid"])
        self.assertTrue(any("repository-wide write scope" in issue for issue in result["issues"]))

    def test_rejects_unknown_dependency(self) -> None:
        run = {
            "run_id": "run_test",
            "decision_type": "software_project_build_task",
            "risk_level": "medium",
        }
        proposal = build_mock_proposal(run)
        proposal["dependencies"].append({"from": "missing_worker", "on": "api_worker"})

        result = validate_architecture_proposal(proposal)

        self.assertFalse(result["valid"])
        self.assertTrue(any("unknown worker" in issue for issue in result["issues"]))

    def test_rejects_high_risk_without_human_gate(self) -> None:
        run = {
            "run_id": "run_test",
            "decision_type": "software_project_build_task",
            "risk_level": "high",
        }
        proposal = build_mock_proposal(run)
        proposal["risk_level"] = "high"
        proposal["action_gate"]["requires_human_review"] = False

        result = validate_architecture_proposal(proposal)

        self.assertFalse(result["valid"])
        self.assertIn("high-risk proposals must require human review.", result["issues"])

    def test_build_approve_and_reject_architecture_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(TASK, root)

            run = build_architecture_proposal(run["run_id"], root, MockProvider())
            proposal_path = root / "data" / "runs" / run["run_id"] / "architecture-proposal.json"
            self.assertTrue(proposal_path.exists())
            self.assertEqual(run["architecture_proposal"]["architecture_id"], f"dynamic/software_project_build_task/{run['run_id']}")

            run = approve_architecture(run["run_id"], "approved for test", root)
            self.assertTrue(any(event["event"] == "architecture_approved" for event in run["audit"]))

            run = reject_architecture(run["run_id"], "revision requested", root)
            self.assertTrue(any(event["event"] == "architecture_rejected" for event in run["audit"]))

    def test_cannot_generate_contracts_before_architecture_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(TASK, root)
            run = build_architecture_proposal(run["run_id"], root, MockProvider())

            with self.assertRaises(ValueError):
                generate_contracts_for_approved_architecture(run["run_id"], root)

    def test_approved_proposal_generates_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(TASK, root)
            run = build_architecture_proposal(run["run_id"], root, MockProvider())
            run = approve_architecture(run["run_id"], "approved", root)
            run = generate_contracts_for_approved_architecture(run["run_id"], root)

            generated_dir = root / "data" / "runs" / run["run_id"] / "generated-contracts"
            self.assertTrue((generated_dir / "ada_scope.json").exists())
            self.assertTrue((generated_dir / "axel_review.json").exists())
            self.assertEqual(len(run["generated_contracts"]), 2)
            review_contract = next(
                contract for contract in run["generated_contracts"]
                if contract["worker_id"] == "axel_review"
            )
            self.assertEqual(review_contract["depends_on"], ["ada_scope"])
            self.assertTrue((root / "data" / "runs" / run["run_id"] / "planning-artifact.json").exists())
            self.assertTrue(
                any(event["event"] == "contracts_generation_completed" for event in run["audit"])
            )

    def test_software_code_task_injects_codebase_explorer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "backend" / "src" / "decision_agent").mkdir(parents=True)
            (root / "public").mkdir()
            (root / "docs").mkdir()
            task = {
                "task_id": "health-endpoint-test",
                "title": "Add GET /api/health endpoint",
                "description": "Add GET /api/health endpoint to backend/src/decision_agent/server.py",
                "desired_outputs": ["backend change", "tests"],
            }

            run = create_run(task, root)
            run = build_architecture_proposal(run["run_id"], root, MockProvider())
            proposal_workers = [
                worker["worker_id"]
                for worker in run["architecture_proposal"]["workers"]
            ]

            self.assertIn("codebase_explorer", proposal_workers)
            self.assertEqual(proposal_workers[0], "codebase_explorer")

            run = approve_architecture(run["run_id"], "approved", root)
            run = generate_contracts_for_approved_architecture(run["run_id"], root)
            contracts = {
                contract["worker_id"]: contract
                for contract in run["generated_contracts"]
            }

            self.assertEqual(contracts["codebase_explorer"]["depends_on"], [])
            self.assertIn("codebase_explorer", contracts["axel_scope"]["depends_on"])
            self.assertIn(
                f"data/runs/{run['run_id']}/outputs/codebase_explorer.json",
                contracts["axel_scope"]["read_paths"],
            )

    def test_unsafe_generated_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(TASK, root)
            run = build_architecture_proposal(run["run_id"], root, MockProvider())
            approve_architecture(run["run_id"], "approved", root)
            proposal_path = root / "data" / "runs" / run["run_id"] / "architecture-proposal.json"
            proposal = run["architecture_proposal"]
            proposal["workers"][0]["write_paths"] = ["**/*"]
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

            with self.assertRaises(ValueError):
                generate_contracts_for_approved_architecture(run["run_id"], root)


if __name__ == "__main__":
    unittest.main()
