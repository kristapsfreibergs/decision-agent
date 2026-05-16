from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.comparison import ComparisonAgent
from decision_agent.modules.agents.eligibility import EligibilityAgent
from decision_agent.modules.agents.evaluation import EvaluationAgent
from decision_agent.modules.agents.evidence import EvidenceAgent
from decision_agent.modules.agents.normalization import NormalizationAgent
from decision_agent.modules.agents.recommendation import RecommendationAgent
from decision_agent.modules.agents.requirement import RequirementAgent
from decision_agent.modules.agents.state_update import StateUpdateAgent
from decision_agent.modules.agents.state_validation import StateValidationAgent
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
        "normalization": NormalizationAgent(),
        "eligibility": EligibilityAgent(),
        "evaluation": EvaluationAgent(),
        "comparison": ComparisonAgent(),
        "recommendation": RecommendationAgent(),
        "state_update": StateUpdateAgent(),
        "state_validation": StateValidationAgent(),
    }

    edges = [
        ("requirement", "evidence"),
        ("evidence", "normalization"),
        ("normalization", "eligibility"),
        ("eligibility", "evaluation"),
        ("evaluation", "comparison"),
        ("comparison", "recommendation"),
        ("recommendation", "state_update"),
        ("state_update", "state_validation"),
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
