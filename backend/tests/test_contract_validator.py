import unittest

from decision_agent.modules.architectures.registry import list_architectures
from decision_agent.modules.contracts.validator import validate_architecture, validate_worker_contract


class ContractValidatorTest(unittest.TestCase):
    def test_validates_software_scaffold_architecture(self) -> None:
        architecture = list_architectures()[0]
        result = validate_architecture(architecture)
        self.assertTrue(result["valid"], result["issues"])

    def test_rejects_repository_wide_write_contracts(self) -> None:
        result = validate_worker_contract(
            {
                "worker_id": "bad_worker",
                "architecture_id": "test/v1",
                "goal": "Do everything.",
                "risk_level": "medium",
                "read_paths": ["README.md"],
                "write_paths": ["**/*"],
                "allowed_tools": ["write_file"],
                "validators": ["write_scope"],
                "max_steps": 1,
                "output_schema": {"type": "object"},
            }
        )

        self.assertFalse(result["valid"])
        self.assertIn("write_paths must not grant repository-wide write access.", result["issues"])

    def test_rejects_direct_final_action_execution(self) -> None:
        result = validate_worker_contract(
            {
                "worker_id": "bad_worker",
                "architecture_id": "test/v1",
                "goal": "Skip gate.",
                "risk_level": "high",
                "read_paths": ["README.md"],
                "write_paths": ["docs/**"],
                "allowed_tools": ["execute_final_action"],
                "validators": ["write_scope"],
                "max_steps": 1,
                "output_schema": {"type": "object"},
            }
        )

        self.assertFalse(result["valid"])
        self.assertIn("workers must not be allowed to execute final actions directly.", result["issues"])


if __name__ == "__main__":
    unittest.main()
