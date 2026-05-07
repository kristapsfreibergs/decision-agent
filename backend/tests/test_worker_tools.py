import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.workers.runner import run_worker
from decision_agent.modules.workers.tools import execute_tool
from decision_agent.shared.providers.base import LLMProvider
from decision_agent.shared.providers.mock import MockProvider


class MultiToolProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "multi-tool-test"

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        return "{}"

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 4096,
        tool_choice: dict | None = None,
    ) -> dict:
        if len(messages) == 1:
            return {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "list_files",
                        "input": {"pattern": "docs/**"},
                    },
                    {
                        "type": "tool_use",
                        "id": "tool_2",
                        "name": "read_file",
                        "input": {"path": "docs/context.md"},
                    },
                ],
                "tool_uses": [
                    {
                        "id": "tool_1",
                        "name": "list_files",
                        "input": {"pattern": "docs/**"},
                    },
                    {
                        "id": "tool_2",
                        "name": "read_file",
                        "input": {"path": "docs/context.md"},
                    },
                ],
            }

        tool_results = messages[-1]["content"]
        if len(tool_results) != 2:
            raise AssertionError("Expected one tool_result per tool_use in the immediate next message.")
        return {
            "stop_reason": "end_turn",
            "content": '{"summary": "done", "files_changed": []}',
            "tool_use": None,
        }


class WorkerToolsTest(unittest.TestCase):
    def test_list_files_treats_recursive_directory_pattern_as_files(self) -> None:
        events = []

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "knowledge/procurement/markets").mkdir(parents=True)
            (root / "knowledge/procurement/markets/vendor-registry.md").write_text(
                "vendors",
                encoding="utf-8",
            )

            result = execute_tool(
                "list_files",
                {"pattern": "knowledge/procurement/markets/**"},
                {
                    "allowed_tools": ["list_files"],
                    "read_paths": ["knowledge/procurement/markets/**"],
                    "write_paths": [],
                },
                root,
                lambda event, **extra: events.append({"event": event, **extra}),
            )

        self.assertIn("knowledge/procurement/markets/vendor-registry.md", result)
        self.assertEqual(events[0]["count"], 1)

    def test_web_search_returns_procurement_fallback_and_audits_call(self) -> None:
        events = []

        with tempfile.TemporaryDirectory() as temp_dir:
            result = execute_tool(
                "web_search",
                {"query": "cloud provider pricing"},
                {
                    "allowed_tools": ["web_search"],
                    "read_paths": [],
                    "write_paths": [],
                },
                Path(temp_dir),
                lambda event, **extra: events.append({"event": event, **extra}),
            )

        self.assertNotIn("ERROR", result)
        self.assertIn("knowledge/procurement/markets", result)
        self.assertEqual(events[0]["event"], "tool_called")
        self.assertEqual(events[0]["tool"], "web_search")
        self.assertEqual(events[0]["query"], "cloud provider pricing")

    def test_runner_replies_to_every_tool_use_in_one_provider_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "data/runs/run_test/audit.jsonl"
            (root / "docs").mkdir()
            (root / "docs/context.md").write_text("context", encoding="utf-8")
            contract = {
                "worker_id": "worker",
                "goal": "Use tools then return JSON.",
                "read_paths": ["docs/**"],
                "write_paths": [],
                "allowed_tools": ["list_files", "read_file"],
                "max_steps": 3,
                "output_schema": {
                    "type": "object",
                    "required": ["summary", "files_changed"],
                    "properties": {
                        "summary": {"type": "string"},
                        "files_changed": {"type": "array"},
                    },
                },
                "validators": ["write_scope"],
            }

            output = run_worker(
                "run_test",
                "worker",
                contract,
                audit_path,
                root,
                MultiToolProvider(),
            )

        self.assertEqual(output["summary"], "done")

    def test_runner_allows_text_fallback_provider_without_tool_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "data/runs/run_test/audit.jsonl"
            contract = {
                "worker_id": "worker",
                "goal": "Return JSON.",
                "read_paths": ["docs/**"],
                "write_paths": ["docs/**"],
                "allowed_tools": ["write_file"],
                "max_steps": 2,
                "output_schema": {
                    "type": "object",
                    "required": ["summary", "files_changed"],
                    "properties": {
                        "summary": {"type": "string"},
                        "files_changed": {"type": "array"},
                    },
                },
                "validators": ["write_scope"],
            }

            output = run_worker(
                "run_test",
                "worker",
                contract,
                audit_path,
                root,
                MockProvider(),
            )

        self.assertIn("summary", output)


if __name__ == "__main__":
    unittest.main()
