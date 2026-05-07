import unittest

from decision_agent.modules.runs.scheduler import (
    get_ready_worker_ids,
    has_active_workers,
    has_blocked_workers,
    is_run_complete,
)


CONTRACTS = [
    {"worker_id": "explorer", "depends_on": []},
    {"worker_id": "implementer", "depends_on": ["explorer"]},
    {"worker_id": "validator", "depends_on": ["implementer"]},
]

PROCUREMENT_CONTRACTS = [
    {"worker_id": "requirement_analyst", "phase_id": "intake", "depends_on": []},
    {"worker_id": "market_scout", "phase_id": "intake", "depends_on": []},
    {"worker_id": "risk_assessor", "phase_id": "intake", "depends_on": []},
    {
        "worker_id": "evaluator",
        "phase_id": "evaluate",
        "depends_on": ["requirement_analyst", "market_scout", "risk_assessor"],
    },
    {"worker_id": "recommender", "phase_id": "recommend", "depends_on": ["evaluator"]},
]

PROCUREMENT_GATES = [
    {
        "id": "human_gate",
        "placement": "recommend",
        "rule": "Human approval required before any vendor commitment or spend.",
    }
]


class SchedulerTest(unittest.TestCase):
    def test_starts_only_dependency_free_workers_first(self) -> None:
        run = {"worker_statuses": {}}

        self.assertEqual(get_ready_worker_ids(run, CONTRACTS), ["explorer"])

    def test_unlocks_downstream_workers_after_validation(self) -> None:
        run = {"worker_statuses": {"explorer": "validated"}}

        self.assertEqual(get_ready_worker_ids(run, CONTRACTS), ["implementer"])

    def test_detects_terminal_rejected_worker(self) -> None:
        run = {
            "worker_statuses": {
                "explorer": "validated",
                "implementer": "rejected",
                "validator": "failed",
            }
        }

        self.assertTrue(is_run_complete(run, CONTRACTS))

    def test_detects_blocked_downstream_worker(self) -> None:
        run = {
            "worker_statuses": {
                "explorer": "validated",
                "implementer": "rejected",
            }
        }

        self.assertFalse(has_active_workers(run, CONTRACTS))
        self.assertTrue(has_blocked_workers(run, CONTRACTS))
        self.assertEqual(get_ready_worker_ids(run, CONTRACTS), [])

    def test_procurement_starts_three_intake_workers_first(self) -> None:
        run = {"worker_statuses": {}}

        self.assertCountEqual(
            get_ready_worker_ids(run, PROCUREMENT_CONTRACTS, PROCUREMENT_GATES),
            ["requirement_analyst", "market_scout", "risk_assessor"],
        )

    def test_procurement_evaluator_unlocks_after_all_intake_validates(self) -> None:
        run = {
            "worker_statuses": {
                "requirement_analyst": "validated",
                "market_scout": "validated",
                "risk_assessor": "validated",
            }
        }

        self.assertEqual(
            get_ready_worker_ids(run, PROCUREMENT_CONTRACTS, PROCUREMENT_GATES),
            ["evaluator"],
        )

    def test_procurement_recommender_waits_for_phase_gate(self) -> None:
        run = {
            "worker_statuses": {
                "requirement_analyst": "validated",
                "market_scout": "validated",
                "risk_assessor": "validated",
                "evaluator": "validated",
            },
            "audit": [],
        }

        self.assertEqual(
            get_ready_worker_ids(run, PROCUREMENT_CONTRACTS, PROCUREMENT_GATES),
            [],
        )

    def test_procurement_recommender_unlocks_after_phase_gate_approval(self) -> None:
        run = {
            "worker_statuses": {
                "requirement_analyst": "validated",
                "market_scout": "validated",
                "risk_assessor": "validated",
                "evaluator": "validated",
            },
            "audit": [{"event": "phase_gate_approved", "phase_id": "recommend"}],
        }

        self.assertEqual(
            get_ready_worker_ids(run, PROCUREMENT_CONTRACTS, PROCUREMENT_GATES),
            ["recommender"],
        )


if __name__ == "__main__":
    unittest.main()
