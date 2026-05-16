from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.advocate import AdvocateAgent
from decision_agent.modules.agents.challenger import ChallengerAgent
from decision_agent.modules.agents.eligibility import EligibilityAgent
from decision_agent.modules.agents.evidence import EvidenceAgent
from decision_agent.modules.agents.recommendation import RecommendationAgent
from decision_agent.modules.agents.requirement import RequirementAgent
from decision_agent.modules.graph.definition import DecisionGraph
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


def build_procurement_graph(
    run_id: str,
    policies: dict[str, Any] | None = None,
    task_context: dict[str, Any] | None = None,
) -> DecisionGraph:
    agents = {
        "requirement": RequirementAgent(),
        "evidence": EvidenceAgent(),
        "eligibility": EligibilityAgent(),
        "advocate": AdvocateAgent(),
        "challenger": ChallengerAgent(),
        "recommendation": RecommendationAgent(),
    }

    edges = [
        ("requirement", "evidence"),
        ("evidence", "eligibility"),
        ("eligibility", "advocate"),
        ("advocate", "challenger"),
        ("challenger", "recommendation"),
    ]

    initial_requirements = {}
    if task_context:
        initial_requirements = {
            "task_title": task_context.get("title", ""),
            "task_summary": task_context.get("description", ""),
            "procurement_subject": task_context.get("title", ""),
        }

    initial_state = DecisionState(
        run_id=run_id,
        domain="procurement",
        phase=DecisionPhase.DRAFT,
        requirements=initial_requirements,
    )

    return DecisionGraph(
        agents=agents,
        edges=edges,
        initial_state=initial_state,
        policies=policies or {},
    )
