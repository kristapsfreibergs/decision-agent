from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decision_agent.modules.agents.base import AgentResult
from decision_agent.modules.graph.definition import DecisionGraph
from decision_agent.modules.operators.base import OperatorContext
from decision_agent.modules.state.decision_state import DecisionState
from decision_agent.shared.audit_log import append_audit_event


@dataclass
class ExecutionResult:
    success: bool
    final_state: DecisionState
    agent_results: list[AgentResult] = field(default_factory=list)
    error: str | None = None


class GraphExecutor:
    def execute(self, graph: DecisionGraph, context: OperatorContext) -> ExecutionResult:
        state = graph.initial_state
        agent_results: list[AgentResult] = []

        for agent_id in graph.topological_order():
            agent = graph.agents[agent_id]
            agent_context = OperatorContext(
                run_id=context.run_id,
                agent_id=agent_id,
                project_root=context.project_root,
                audit_path=context.audit_path,
                provider=context.provider,
                layer_config=context.layer_config,
                policies=context.policies,
                memory=context.memory,
            )

            append_audit_event(
                context.audit_path,
                {"event": "agent_started", "run_id": context.run_id, "agent_id": agent_id},
            )

            result = agent.run(state, agent_context)
            agent_results.append(result)

            # Write agent output
            self._persist_agent_output(
                context.project_root, context.run_id, agent_id, result,
            )

            if not result.success:
                append_audit_event(
                    context.audit_path,
                    {
                        "event": "agent_failed",
                        "run_id": context.run_id,
                        "agent_id": agent_id,
                        "error": result.error or "unknown",
                    },
                )
                return ExecutionResult(
                    success=False,
                    final_state=result.state_after,
                    agent_results=agent_results,
                    error=f"Agent {agent_id} failed: {result.error}",
                )

            state = result.state_after
            append_audit_event(
                context.audit_path,
                {
                    "event": "state_transitioned",
                    "run_id": context.run_id,
                    "agent_id": agent_id,
                    "phase": state.phase.value,
                },
            )

        # Persist final decision state
        self._persist_decision_state(context.project_root, context.run_id, state)

        return ExecutionResult(
            success=True,
            final_state=state,
            agent_results=agent_results,
        )

    def _persist_agent_output(
        self,
        project_root: Path,
        run_id: str,
        agent_id: str,
        result: AgentResult,
    ) -> None:
        out_dir = project_root / "data" / "runs" / run_id / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "agent_id": agent_id,
            "success": result.success,
        }
        if result.error:
            data["error"] = result.error
        for op_result in result.operator_results:
            if op_result.data:
                data.update(op_result.data)
        (out_dir / f"{agent_id}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _persist_decision_state(
        self,
        project_root: Path,
        run_id: str,
        state: DecisionState,
    ) -> None:
        run_dir = project_root / "data" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "decision-state.json").write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
