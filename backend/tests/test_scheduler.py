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


if __name__ == "__main__":
    unittest.main()
