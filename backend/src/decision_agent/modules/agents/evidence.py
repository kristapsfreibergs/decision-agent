from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_extract import ExtractOperator
from decision_agent.modules.operators.mem_search import MemorySearchOperator
from decision_agent.modules.state.decision_state import DecisionState


class EvidenceAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="evidence",
            operators=[
                MemorySearchOperator(),
                ExtractOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=None,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "mem_search":
            return {"query": state.requirements.get("procurement_subject", "")}
        if op_name == "extract":
            return {
                "contract": self._make_contract(state),
                "state_patch_key": "evidence",
            }
        if op_name == "update_state":
            return {"patch": {"evidence": state.evidence}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        market_file = f"data/runs/{state.run_id}/workspace/market_research.md"
        risk_file = f"data/runs/{state.run_id}/workspace/risk_assessment.md"

        hard_constraints = state.requirements.get("hard_constraints", [])
        constraint_fields = sorted({
            c["field"] for c in hard_constraints
            if isinstance(c, dict) and c.get("field")
        }) or [
            "unit_price_eur", "total_price_eur", "iso_27001_valid", "gdpr_dpa_status",
            "gdpr_dpa_blocker", "ships_from_eu_warehouse", "ram_gb", "ssd_tb",
            "onsite_warranty_years", "architecture", "cpu_physical_performance_cores",
            "quote_valid_until", "delivery_date_estimate",
        ]
        return {
            "worker_id": f"{self.agent_id}_extract",
            "goal": (
                "Research the vendor market for this procurement. "
                "Read all available offer files — structured JSON and narrative markdown.\n\n"
                f"1. Write a market research summary to {market_file} covering what you found.\n"
                f"2. Write a risk assessment to {risk_file} rating each risk dimension "
                "(vendor concentration, delivery, compliance, budget, reputational) as "
                "LOW / MEDIUM / HIGH with a brief phrase.\n\n"
                "Then return a structured vendor list. For each vendor extract every factual "
                "field you can find — especially these constraint fields that downstream "
                f"filtering will need: {constraint_fields}. "
                "Also include: name, model, pricing, delivery dates, certifications, compliance "
                "status, hardware specs, lead_time_weeks. Do not score or rank vendors — report facts only.\n\n"
                "Return:\n"
                '{"status": "ok", "written_to": ["<market_path>", "<risk_path>"], '
                '"summary": "<one sentence>", '
                '"active_vendors": [{"name": "<vendor>", <all factual fields found>}]}'
            ),
            "read_paths": [
                "archive/knowledge/procurement/**",
            ],
            "write_paths": [market_file, risk_file],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "validators": ["write_scope"],
            "max_steps": 10,
            "output_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "written_to": {},
                    "summary": {"type": "string"},
                    "active_vendors": {"type": "array"},
                },
                "required": ["status", "active_vendors"],
            },
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }
