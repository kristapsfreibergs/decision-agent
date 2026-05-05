import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.runs.service import create_run


class RunsServiceTest(unittest.TestCase):
    def test_creates_auditable_run_with_worker_contracts(self) -> None:
        task = {
            "task_id": "build-decision-agent-test",
            "title": "Build backend runtime",
            "description": "Implement a Python backend for the decision harness.",
            "desired_outputs": ["contracts", "audit log"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = create_run(task, root=root)

            self.assertEqual(run["architecture_id"], "software-scaffold-build/v1")
            self.assertEqual(len(run["contracts"]), 5)
            self.assertTrue(all(contract["work_layer"] for contract in run["contracts"]))

            run_record_path = root / "data" / "runs" / run["run_id"] / "run-record.json"
            run_record = json.loads(run_record_path.read_text())
            self.assertNotIn("status", run_record)
            self.assertEqual(run["status"], "ready")

            audit = (root / "data" / "runs" / run["run_id"] / "audit.jsonl").read_text()
            self.assertIn("run_created", audit)
            self.assertIn("contract_created", audit)
            self.assertIn("run_ready", audit)


if __name__ == "__main__":
    unittest.main()
