import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.runs.service import (
    approve_architecture,
    build_architecture_proposal,
    create_run,
    generate_contracts_for_approved_architecture,
    read_run,
)
from decision_agent.shared.providers.mock import MockProvider
from decision_agent.shared.providers.base import LLMProvider
from decision_agent.server import _can_execute_contract


class ProcurementProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "procurement-test"

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        if "task domain classifier" in system:
            return json.dumps({"domain": "procurement"})
        return json.dumps({"shape": "funnel", "reasoning": "test", "modifiers": []})


def _procurement_task() -> dict:
    return {
        "title": "Select cloud provider for backend infrastructure",
        "description": (
            "We need to select a cloud provider for our decision-agent backend. "
            "Budget ceiling: EUR 50,000/year. Must be GDPR compliant. "
            "Evaluate AWS, Azure, GCP, and Hetzner."
        ),
    }


class ProcurementE2ETest(unittest.TestCase):
    def test_procurement_task_routes_to_procurement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = create_run(_procurement_task(), Path(temp_dir))

        self.assertEqual(run["decision_type"], "procurement")

    def test_procurement_proposal_has_five_domain_workers_and_no_codebase_explorer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(_procurement_task(), root)
            run = build_architecture_proposal(run["run_id"], root, ProcurementProvider())

            worker_ids = [
                worker["worker_id"]
                for worker in run["architecture_proposal"]["workers"]
            ]

        self.assertEqual(
            worker_ids,
            [
                "requirement_analyst",
                "market_scout",
                "risk_assessor",
                "evaluator",
                "recommender",
            ],
        )
        self.assertNotIn("codebase_explorer", worker_ids)

    def test_procurement_catalog_is_selected_even_with_mock_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(_procurement_task(), root)
            run = build_architecture_proposal(run["run_id"], root, MockProvider())

        self.assertEqual(run["architecture_proposal"]["decision_type"], "procurement")
        self.assertEqual(len(run["architecture_proposal"]["workers"]), 5)

    def test_procurement_generated_contract_dependencies_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(_procurement_task(), root)
            run = build_architecture_proposal(run["run_id"], root, ProcurementProvider())
            run = approve_architecture(run["run_id"], "approved", root)
            run = generate_contracts_for_approved_architecture(run["run_id"], root)

            contracts = {
                contract["worker_id"]: contract
                for contract in run["generated_contracts"]
            }

        self.assertEqual(contracts["requirement_analyst"]["depends_on"], [])
        self.assertEqual(contracts["market_scout"]["depends_on"], [])
        self.assertEqual(contracts["risk_assessor"]["depends_on"], [])
        self.assertCountEqual(
            contracts["evaluator"]["depends_on"],
            ["requirement_analyst", "market_scout", "risk_assessor"],
        )
        self.assertEqual(contracts["recommender"]["depends_on"], ["evaluator"])
        self.assertIn(
            f"data/runs/{run['run_id']}/outputs/evaluator.json",
            contracts["recommender"]["read_paths"],
        )

    def test_manual_execute_is_blocked_until_recommend_phase_gate_is_approved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(_procurement_task(), root)
            run = build_architecture_proposal(run["run_id"], root, ProcurementProvider())
            run = approve_architecture(run["run_id"], "approved", root)
            run = generate_contracts_for_approved_architecture(run["run_id"], root)
            recommender = next(
                contract
                for contract in run["generated_contracts"]
                if contract["worker_id"] == "recommender"
            )

            allowed, message = _can_execute_contract(run, recommender)
            approved_run = {
                **run,
                "audit": [
                    *run["audit"],
                    {"event": "phase_gate_approved", "phase_id": "recommend"},
                ],
            }
            allowed_after_approval, _ = _can_execute_contract(approved_run, recommender)

        self.assertFalse(allowed)
        self.assertIn("Phase gate", message)
        self.assertTrue(allowed_after_approval)

    def test_read_run_normalizes_preview_paths_in_generated_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(_procurement_task(), root)
            run_dir = root / "data" / "runs" / run["run_id"]
            generated_dir = run_dir / "generated-contracts"
            generated_dir.mkdir()
            contract = {
                "worker_id": "market_scout",
                "run_id": "preview",
                "read_paths": [
                    "knowledge/procurement/markets/**",
                    "data/runs/preview/outputs/requirement_analyst.json",
                ],
                "write_paths": ["data/runs/preview/workspace/market_research.md"],
            }
            (generated_dir / "market_scout.json").write_text(
                json.dumps(contract),
                encoding="utf-8",
            )

            loaded = read_run(run["run_id"], root)
            loaded_contract = loaded["generated_contracts"][0]

        self.assertEqual(loaded_contract["run_id"], run["run_id"])
        self.assertIn(
            f"data/runs/{run['run_id']}/outputs/requirement_analyst.json",
            loaded_contract["read_paths"],
        )
        self.assertEqual(
            loaded_contract["write_paths"],
            [f"data/runs/{run['run_id']}/workspace/market_research.md"],
        )


if __name__ == "__main__":
    unittest.main()
