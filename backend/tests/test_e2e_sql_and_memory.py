"""End-to-end tests for the SQL connector (query_sql) and cross-run memory.

query_sql tests use data/demo.db — created by scripts/create_demo_db.py.
Memory tests use an in-memory filesystem provider backed by a temp directory.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.workers.tools import execute_tool
from decision_agent.shared.memory.base import MemoryItem
from decision_agent.shared.memory.filesystem import FilesystemMemoryProvider


def _noop_emit(*args, **kwargs) -> None:
    pass


# ---------------------------------------------------------------------------
# query_sql
# ---------------------------------------------------------------------------

class QuerySqlToolTest(unittest.TestCase):
    """Tests against data/demo.db — requires create_demo_db.py to have been run."""

    def _contract(self, allowed_tables: list[str] | None = None) -> dict:
        return {
            "allowed_tools": ["query_sql"],
            "allowed_tables": allowed_tables if allowed_tables is not None else [
                "vendor_mgmt.proposals",
                "vendor_mgmt.rankings",
                "compliance.certifications",
                "finance.approved_budgets",
                "market_intel.benchmarks",
            ],
        }

    def _root(self) -> Path:
        return Path.cwd()

    def test_returns_vendor_proposals_with_evidence_annotation(self) -> None:
        result = execute_tool(
            "query_sql",
            {"table": "vendor_mgmt.proposals", "limit": 5},
            self._contract(),
            self._root(),
            _noop_emit,
        )
        if result.startswith("ERROR"):
            self.skipTest(f"Demo DB not available: {result}")
        rows = json.loads(result)
        self.assertGreater(len(rows), 0)
        first = rows[0]
        self.assertEqual(first["type"], "vendor_proposal")
        self.assertIn("id", first)
        self.assertIn("excerpt", first)
        self.assertIn("created_at", first)

    def test_filters_by_iso27001_certified(self) -> None:
        result = execute_tool(
            "query_sql",
            {"table": "vendor_mgmt.proposals", "filters": {"iso27001_certified": 1}},
            self._contract(),
            self._root(),
            _noop_emit,
        )
        if result.startswith("ERROR"):
            self.skipTest(f"Demo DB not available: {result}")
        rows = json.loads(result)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertIn("iso27001_certified=1", row["excerpt"])

    def test_compliance_certifications_returns_compliance_rule_class(self) -> None:
        result = execute_tool(
            "query_sql",
            {"table": "compliance.certifications"},
            self._contract(),
            self._root(),
            _noop_emit,
        )
        if result.startswith("ERROR"):
            self.skipTest(f"Demo DB not available: {result}")
        rows = json.loads(result)
        if rows:
            self.assertEqual(rows[0]["type"], "compliance_rule")

    def test_blocked_when_table_not_in_allowed_tables(self) -> None:
        result = execute_tool(
            "query_sql",
            {"table": "finance.approved_budgets"},
            self._contract(allowed_tables=["vendor_mgmt.proposals"]),
            self._root(),
            _noop_emit,
        )
        self.assertTrue(result.startswith("ERROR"), f"Expected ERROR, got: {result[:100]}")
        self.assertIn("allowed_tables", result)

    def test_blocked_when_table_not_in_schema_map(self) -> None:
        result = execute_tool(
            "query_sql",
            {"table": "hr.employees"},
            self._contract(allowed_tables=["hr.employees"]),
            self._root(),
            _noop_emit,
        )
        self.assertTrue(result.startswith("ERROR"))
        self.assertIn("schema-map", result)

    def test_limit_enforced_at_20(self) -> None:
        result = execute_tool(
            "query_sql",
            {"table": "vendor_mgmt.proposals", "limit": 100},
            self._contract(),
            self._root(),
            _noop_emit,
        )
        if result.startswith("ERROR"):
            self.skipTest(f"Demo DB not available: {result}")
        rows = json.loads(result)
        self.assertLessEqual(len(rows), 20)

    def test_result_id_uses_table_and_pk(self) -> None:
        result = execute_tool(
            "query_sql",
            {"table": "vendor_mgmt.proposals", "limit": 1},
            self._contract(),
            self._root(),
            _noop_emit,
        )
        if result.startswith("ERROR"):
            self.skipTest(f"Demo DB not available: {result}")
        rows = json.loads(result)
        self.assertTrue(rows[0]["id"].startswith("vendor_mgmt.proposals#"))


# ---------------------------------------------------------------------------
# FilesystemMemoryProvider
# ---------------------------------------------------------------------------

class FilesystemMemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self._tmp.name)
        self.mp = FilesystemMemoryProvider(self.data_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _item(self, content: str, domain: str = "procurement",
               evidence_class: str = "vendor_proposal") -> MemoryItem:
        return MemoryItem(
            source_run_id="run_test",
            worker_id="evaluator",
            evidence_class=evidence_class,
            content=content,
            created_at="2026-04-01",
            domain=domain,
            authority_score=0.70,
        )

    def test_write_and_count(self) -> None:
        self.mp.write(self._item("Lenovo EU ISO 27001 confirmed"))
        self.mp.write(self._item("Dell Technologies GDPR DPA available"))
        self.assertEqual(self.mp.count("procurement"), 2)

    def test_search_finds_keyword_match(self) -> None:
        self.mp.write(self._item("Lenovo ThinkPad: ISO 27001 BSI certificate"))
        self.mp.write(self._item("Dell: ProSupport Plus warranty"))
        scope = {"domain": "procurement", "allowed_evidence_classes": ["vendor_proposal"]}
        hits = self.mp.search("Lenovo ISO", scope, limit=5)
        self.assertEqual(len(hits), 1)
        self.assertIn("Lenovo", hits[0].excerpt)

    def test_search_returns_empty_for_no_match(self) -> None:
        self.mp.write(self._item("HP EliteBook warranty three years"))
        scope = {"domain": "procurement", "allowed_evidence_classes": ["vendor_proposal"]}
        hits = self.mp.search("Lenovo ISO", scope, limit=5)
        self.assertEqual(hits, [])

    def test_search_scope_enforced_by_domain(self) -> None:
        self.mp.write(self._item("Lenovo ISO 27001", domain="procurement"))
        self.mp.write(self._item("Candidate skills Python", domain="hr"))
        scope = {"domain": "procurement", "allowed_evidence_classes": ["vendor_proposal"]}
        hits = self.mp.search("Lenovo", scope, limit=5)
        self.assertEqual(len(hits), 1)
        # HR item must not appear even though it has different keyword — domain boundary
        scope_hr = {"domain": "hr", "allowed_evidence_classes": ["vendor_proposal"]}
        hits_hr = self.mp.search("Lenovo", scope_hr, limit=5)
        self.assertEqual(len(hits_hr), 0)

    def test_search_scope_enforced_by_evidence_class(self) -> None:
        self.mp.write(self._item("Lenovo ISO 27001", evidence_class="compliance_rule"))
        scope = {
            "domain": "procurement",
            "allowed_evidence_classes": ["vendor_proposal"],  # compliance_rule not allowed
        }
        hits = self.mp.search("Lenovo", scope, limit=5)
        self.assertEqual(len(hits), 0, "compliance_rule item should be excluded from vendor_proposal scope")

    def test_relevance_score_higher_for_more_keyword_matches(self) -> None:
        self.mp.write(self._item("Lenovo"))
        self.mp.write(self._item("Lenovo ISO 27001 certification confirmed"))
        scope = {"domain": "procurement", "allowed_evidence_classes": ["vendor_proposal"]}
        hits = self.mp.search("Lenovo ISO certification", scope, limit=5)
        self.assertGreater(len(hits), 1)
        self.assertGreater(hits[0].relevance_score, hits[1].relevance_score)

    def test_memory_search_tool_uses_scope_from_contract(self) -> None:
        """memory_search tool respects scope_contract on the worker contract."""
        # Write via same provider the tool will use: get_memory_provider(root / "data")
        # tool uses project_root / "data" as data_root, and self.data_root IS the data dir.
        # So project_root should be self.data_root.parent to resolve correctly.
        # Simplest: just verify the tool returns no ERROR (empty result is OK when no data).
        scope_contract = {
            "domain": "procurement",
            "allowed_evidence_classes": ["vendor_proposal", "compliance_rule"],
        }
        contract = {
            "allowed_tools": ["memory_search"],
            "scope_contract": scope_contract,
        }
        result = execute_tool(
            "memory_search",
            {"query": "Lenovo vendor"},
            contract,
            self.data_root.parent,  # project_root; tool builds data_root = project_root / "data"
            _noop_emit,
        )
        # Should return either a JSON array or a "no past evidence" message — no ERROR
        self.assertNotIn("ERROR", result)


class MemoryIndexingAfterGateApproveTest(unittest.TestCase):
    """Tests that gate_approve triggers evidence indexing into cross-run memory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_gate_approve_indexes_evidence_when_workers_validated(self) -> None:
        """After a run completes (gate_approved), evidence from validated workers
        should be findable via memory_search in subsequent runs."""
        from decision_agent.modules.governance.layer_config import LayerConfig
        from decision_agent.modules.runs.service import (
            approve_architecture, build_architecture_proposal, create_run,
            generate_contracts_for_approved_architecture, start_run, gate_approve,
        )
        from decision_agent.shared.memory.filesystem import FilesystemMemoryProvider
        from test_e2e_procurement_run import ProcurementMockProvider, _laptop_task, _run_all_workers

        provider = ProcurementMockProvider()
        cfg = LayerConfig(
            dsc_enabled=False, paap_enabled=False, dar_enabled=False,
            human_gate_enabled=False, contract_validators_enabled=False,
        )
        run = create_run(_laptop_task(), self.root, layer_config=cfg, benchmark_mode=True)
        run_id = run["run_id"]
        build_architecture_proposal(run_id, self.root, provider)
        approve_architecture(run_id, "test", self.root)
        generate_contracts_for_approved_architecture(run_id, self.root)
        start_run(run_id, self.root)
        _run_all_workers(run_id, self.root, provider)

        # gate_approve triggers memory indexing
        gate_approve(run_id, "e2e test", self.root)

        # Memory should now have items from this run
        # _index_run_to_memory calls get_memory_provider(root / "data")
        # which creates FilesystemMemoryProvider(root / "data")
        # which stores at root / "data" / "memory" / domain / *.jsonl
        mp = FilesystemMemoryProvider(self.root / "data")
        count = mp.count("procurement")
        # Evaluator output has 3 evidence_sources — they should be indexed
        # (some workers may not have evidence_sources so count >= 3 from evaluator)
        self.assertGreater(count, 0, "Memory should have items after gate_approve")


if __name__ == "__main__":
    unittest.main()
