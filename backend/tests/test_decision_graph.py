from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from decision_agent.modules.agents.base import AgentBase, AgentResult
from decision_agent.modules.graph.definition import DecisionGraph
from decision_agent.modules.graph.domain_graphs.procurement import build_procurement_graph
from decision_agent.modules.graph.executor import ExecutionResult, GraphExecutor
from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState
from decision_agent.modules.state.transitions import VALID_TRANSITIONS, validate_transition


class TestDecisionState(unittest.TestCase):
    def test_initial_state(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        self.assertEqual(state.phase, DecisionPhase.DRAFT)
        self.assertEqual(state.requirements, {})
        self.assertEqual(state.agent_history, [])

    def test_apply_patch_merges_dicts(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement", requirements={"a": 1})
        patched = state.apply_patch({"requirements": {"b": 2}})
        self.assertEqual(patched.requirements, {"a": 1, "b": 2})

    def test_apply_patch_appends_lists(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement", scope_violations=["v1"])
        patched = state.apply_patch({"scope_violations": ["v2"]})
        self.assertEqual(patched.scope_violations, ["v1", "v2"])

    def test_apply_patch_replaces_scalars(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        patched = state.apply_patch({"domain": "cv_evaluation"})
        self.assertEqual(patched.domain, "cv_evaluation")

    def test_apply_patch_ignores_unknown_fields(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        patched = state.apply_patch({"nonexistent_field": "value"})
        self.assertEqual(patched, state)

    def test_transition_to_valid(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        new_state = state.transition_to(DecisionPhase.EVIDENCE_INCOMPLETE)
        self.assertEqual(new_state.phase, DecisionPhase.EVIDENCE_INCOMPLETE)
        self.assertEqual(new_state.agent_history, ["evidence_incomplete"])

    def test_transition_to_invalid_raises(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        with self.assertRaises(ValueError) as ctx:
            state.transition_to(DecisionPhase.VALIDATED)
        self.assertIn("Invalid state transition", str(ctx.exception))

    def test_to_dict_serializable(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        data = state.to_dict()
        self.assertEqual(data["phase"], "draft")
        json.dumps(data)  # should not raise

    def test_immutability(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        with self.assertRaises(AttributeError):
            state.phase = DecisionPhase.ELIGIBLE  # type: ignore[misc]


class TestTransitions(unittest.TestCase):
    def test_all_phases_have_entry(self) -> None:
        for phase in DecisionPhase:
            self.assertIn(phase, VALID_TRANSITIONS)

    def test_validated_is_terminal(self) -> None:
        self.assertEqual(VALID_TRANSITIONS[DecisionPhase.VALIDATED], [])

    def test_full_chain(self) -> None:
        state = DecisionState(run_id="r1", domain="procurement")
        phases = [
            DecisionPhase.EVIDENCE_INCOMPLETE,
            DecisionPhase.ELIGIBLE,
            DecisionPhase.EVALUATED,
            DecisionPhase.RECOMMENDED,
            DecisionPhase.APPROVED,
            DecisionPhase.STATE_UPDATED,
            DecisionPhase.VALIDATED,
        ]
        for phase in phases:
            state = state.transition_to(phase)
        self.assertEqual(state.phase, DecisionPhase.VALIDATED)
        self.assertEqual(len(state.agent_history), 7)


class TestDecisionGraph(unittest.TestCase):
    def test_topological_order_linear(self) -> None:
        graph = DecisionGraph(
            agents={"a": None, "b": None, "c": None},
            edges=[("a", "b"), ("b", "c")],
            initial_state=DecisionState(run_id="r1", domain="test"),
        )
        self.assertEqual(graph.topological_order(), ["a", "b", "c"])

    def test_topological_order_fan_out(self) -> None:
        graph = DecisionGraph(
            agents={"a": None, "b": None, "c": None, "d": None},
            edges=[("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
            initial_state=DecisionState(run_id="r1", domain="test"),
        )
        order = graph.topological_order()
        self.assertEqual(order[0], "a")
        self.assertEqual(order[-1], "d")
        self.assertIn("b", order)
        self.assertIn("c", order)

    def test_cycle_raises(self) -> None:
        graph = DecisionGraph(
            agents={"a": None, "b": None},
            edges=[("a", "b"), ("b", "a")],
            initial_state=DecisionState(run_id="r1", domain="test"),
        )
        with self.assertRaises(ValueError) as ctx:
            graph.topological_order()
        self.assertIn("cycle", str(ctx.exception).lower())

    def test_predecessors(self) -> None:
        graph = DecisionGraph(
            agents={"a": None, "b": None, "c": None},
            edges=[("a", "c"), ("b", "c")],
            initial_state=DecisionState(run_id="r1", domain="test"),
        )
        self.assertEqual(sorted(graph.predecessors("c")), ["a", "b"])
        self.assertEqual(graph.predecessors("a"), [])

    def test_successors(self) -> None:
        graph = DecisionGraph(
            agents={"a": None, "b": None, "c": None},
            edges=[("a", "b"), ("a", "c")],
            initial_state=DecisionState(run_id="r1", domain="test"),
        )
        self.assertEqual(sorted(graph.successors("a")), ["b", "c"])


class TestProcurementGraph(unittest.TestCase):
    def test_build_has_9_agents(self) -> None:
        graph = build_procurement_graph("r1")
        self.assertEqual(len(graph.agents), 9)

    def test_build_has_8_edges(self) -> None:
        graph = build_procurement_graph("r1")
        self.assertEqual(len(graph.edges), 8)

    def test_topological_order_starts_with_requirement(self) -> None:
        graph = build_procurement_graph("r1")
        order = graph.topological_order()
        self.assertEqual(order[0], "requirement")
        self.assertEqual(order[-1], "state_validation")

    def test_task_context_populates_initial_state(self) -> None:
        graph = build_procurement_graph(
            "r1",
            task_context={"title": "Buy laptops", "description": "100 dev laptops"},
        )
        self.assertEqual(graph.initial_state.requirements["task_title"], "Buy laptops")
        self.assertEqual(graph.initial_state.requirements["task_summary"], "100 dev laptops")

    def test_all_agents_have_operators(self) -> None:
        graph = build_procurement_graph("r1")
        for agent_id, agent in graph.agents.items():
            self.assertGreater(len(agent.operators), 0, f"Agent {agent_id} has no operators")


class TestDeterministicRubric(unittest.TestCase):
    def test_apply_rubric_computes_weighted_scores(self) -> None:
        from decision_agent.modules.agents.evaluation import apply_rubric

        vendors = [
            {"vendor": "A", "price": 4, "delivery": 3, "quality": 2, "compliance": 4},
            {"vendor": "B", "price": 2, "delivery": 4, "quality": 4, "compliance": 1},
        ]
        scored = apply_rubric(vendors)
        # A: 4*0.30 + 3*0.20 + 2*0.25 + 4*0.25 = 1.2 + 0.6 + 0.5 + 1.0 = 3.3
        self.assertAlmostEqual(scored[0]["total_score"], 3.3, places=3)
        # B: 2*0.30 + 4*0.20 + 4*0.25 + 1*0.25 = 0.6 + 0.8 + 1.0 + 0.25 = 2.65
        self.assertAlmostEqual(scored[1]["total_score"], 2.65, places=3)

    def test_apply_rubric_handles_missing_criteria(self) -> None:
        from decision_agent.modules.agents.evaluation import apply_rubric

        vendors = [{"vendor": "C", "price": 3}]  # missing delivery, quality, compliance
        scored = apply_rubric(vendors)
        # 3*0.30 + 0 + 0 + 0 = 0.9
        self.assertAlmostEqual(scored[0]["total_score"], 0.9, places=3)

    def test_apply_rubric_custom_weights(self) -> None:
        from decision_agent.modules.agents.evaluation import apply_rubric

        vendors = [{"vendor": "D", "cost": 4, "speed": 2}]
        scored = apply_rubric(vendors, rubric={"cost": 0.6, "speed": 0.4})
        # 4*0.6 + 2*0.4 = 2.4 + 0.8 = 3.2
        self.assertAlmostEqual(scored[0]["total_score"], 3.2, places=3)

    def test_apply_rubric_non_numeric_defaults_to_zero(self) -> None:
        from decision_agent.modules.agents.evaluation import apply_rubric

        vendors = [{"vendor": "E", "price": "not a number", "delivery": 3, "quality": 2, "compliance": 1}]
        scored = apply_rubric(vendors)
        # 0*0.30 + 3*0.20 + 2*0.25 + 1*0.25 = 0 + 0.6 + 0.5 + 0.25 = 1.35
        self.assertAlmostEqual(scored[0]["total_score"], 1.35, places=3)

    def test_llm_never_produces_scores(self) -> None:
        """EvaluationAgent uses ExtractOperator (LLM), not ExplainOperator for scoring."""
        from decision_agent.modules.agents.evaluation import EvaluationAgent
        from decision_agent.modules.operators.llm_extract import ExtractOperator
        from decision_agent.modules.operators.llm_explain import ExplainOperator

        agent = EvaluationAgent()
        op_types = [type(op) for op in agent.operators]
        self.assertIn(ExtractOperator, op_types)
        self.assertNotIn(ExplainOperator, op_types)


class TestOperators(unittest.TestCase):
    def test_normalize_currency(self) -> None:
        from decision_agent.modules.operators.det_normalize import NormalizeOperator

        op = NormalizeOperator()
        result = op.execute(
            None,
            {"data": {"price": "€1,500.00", "name": "  vendor  "}},
            MagicMock(),
        )
        self.assertTrue(result.success)
        self.assertEqual(result.data["normalized"]["price"]["amount"], 1500.0)
        self.assertEqual(result.data["normalized"]["price"]["currency"], "EUR")
        self.assertEqual(result.data["normalized"]["name"], "vendor")

    def test_filter_eliminates_failing_candidates(self) -> None:
        from decision_agent.modules.operators.det_filter import FilterOperator

        op = FilterOperator()
        result = op.execute(
            None,
            {
                "candidates": [
                    {"name": "A", "iso": True},
                    {"name": "B", "iso": False},
                ],
                "hard_constraints": [{"field": "iso", "op": "truthy", "value": True}],
            },
            MagicMock(),
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.data["eligible"]), 1)
        self.assertEqual(result.data["eligible"][0]["name"], "A")
        self.assertEqual(len(result.data["eliminated"]), 1)

    def test_rank_sorts_descending(self) -> None:
        from decision_agent.modules.operators.det_rank import RankOperator

        op = RankOperator()
        result = op.execute(
            None,
            {"scores": [{"name": "A", "total_score": 3}, {"name": "B", "total_score": 5}]},
            MagicMock(),
        )
        self.assertTrue(result.success)
        self.assertEqual(result.data["ranked"][0]["name"], "B")
        self.assertEqual(result.data["ranked"][0]["rank"], 1)

    def test_validate_state_checks_required_fields(self) -> None:
        from decision_agent.modules.operators.det_validate_state import ValidateStateOperator

        op = ValidateStateOperator()
        state = DecisionState(run_id="r1", domain="procurement")
        result = op.execute(state, {"required_fields": ["requirements"]}, MagicMock())
        self.assertFalse(result.success)
        self.assertIn("requirements", result.error)

    def test_validate_state_passes_with_data(self) -> None:
        from decision_agent.modules.operators.det_validate_state import ValidateStateOperator

        op = ValidateStateOperator()
        state = DecisionState(
            run_id="r1", domain="procurement",
            requirements={"budget": 200000},
            recommendation={"vendor": "X"},
        )
        result = op.execute(state, {"required_fields": ["requirements", "recommendation"]}, MagicMock())
        self.assertTrue(result.success)

    def test_mem_search_skips_when_no_memory(self) -> None:
        from decision_agent.modules.operators.mem_search import MemorySearchOperator

        op = MemorySearchOperator()
        ctx = MagicMock()
        ctx.memory = None
        result = op.execute(None, {"query": "test"}, ctx)
        self.assertTrue(result.success)
        self.assertTrue(result.data.get("mem_search_skipped"))

    def test_mem_write_skips_when_no_memory(self) -> None:
        from decision_agent.modules.operators.mem_write import MemoryWriteOperator

        op = MemoryWriteOperator()
        ctx = MagicMock()
        ctx.memory = None
        result = op.execute(None, {"evidence_items": [{"content": "test"}]}, ctx)
        self.assertTrue(result.success)
        self.assertTrue(result.data.get("mem_write_skipped"))


class TestGraphExecutor(unittest.TestCase):
    def test_executor_runs_simple_agent_chain(self) -> None:
        """Test executor with a minimal 2-agent chain using stub operators."""
        class StubOp(OperatorBase):
            def __init__(self, name: str, patch: dict) -> None:
                super().__init__(name, is_deterministic=True)
                self._patch = patch

            def execute(self, state, config, context) -> OperatorResult:
                return OperatorResult(success=True, state_patch=self._patch)

        class StubAgent(AgentBase):
            def _operator_config(self, op_name, state) -> dict:
                return {}

        agent_a = StubAgent(
            "a",
            [StubOp("op1", {"requirements": {"extracted": True}})],
            target_phase=DecisionPhase.EVIDENCE_INCOMPLETE,
        )
        agent_b = StubAgent(
            "b",
            [StubOp("op2", {"evidence": {"found": True}})],
            target_phase=DecisionPhase.ELIGIBLE,
        )

        state = DecisionState(run_id="r1", domain="test")
        graph = DecisionGraph(
            agents={"a": agent_a, "b": agent_b},
            edges=[("a", "b")],
            initial_state=state,
        )

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            audit_path = root / "data" / "runs" / "r1" / "audit.jsonl"
            audit_path.parent.mkdir(parents=True, exist_ok=True)

            from decision_agent.modules.governance.layer_config import LayerConfig

            context = OperatorContext(
                run_id="r1",
                agent_id="executor",
                project_root=root,
                audit_path=audit_path,
                provider=None,
                layer_config=LayerConfig.full(),
            )

            executor = GraphExecutor()
            result = executor.execute(graph, context)

            self.assertTrue(result.success)
            self.assertEqual(result.final_state.phase, DecisionPhase.ELIGIBLE)
            self.assertEqual(result.final_state.requirements, {"extracted": True})
            self.assertEqual(result.final_state.evidence, {"found": True})
            self.assertEqual(len(result.agent_results), 2)

            # Check outputs were persisted
            self.assertTrue((root / "data" / "runs" / "r1" / "outputs" / "a.json").exists())
            self.assertTrue((root / "data" / "runs" / "r1" / "outputs" / "b.json").exists())

            # Check decision-state.json was persisted
            state_file = root / "data" / "runs" / "r1" / "decision-state.json"
            self.assertTrue(state_file.exists())
            persisted = json.loads(state_file.read_text())
            self.assertEqual(persisted["phase"], "eligible")

            # Check audit log
            self.assertTrue(audit_path.exists())


class TestNewEventVocabulary(unittest.TestCase):
    def test_new_events_importable(self) -> None:
        from decision_agent.modules.runs.state import (
            AGENT_COMPLETED,
            AGENT_FAILED,
            AGENT_STARTED,
            DECISION_OUTCOME_RECORDED,
            EVIDENCE_PERSISTED,
            MEMORY_SEARCHED,
            OPERATOR_COMPLETED,
            STATE_TRANSITIONED,
        )
        self.assertEqual(AGENT_STARTED, "agent_started")
        self.assertEqual(STATE_TRANSITIONED, "state_transitioned")


if __name__ == "__main__":
    unittest.main()
