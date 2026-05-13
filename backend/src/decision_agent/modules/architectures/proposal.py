from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.conversion import artifact_to_proposal
from decision_agent.modules.architectures.planning import build_planning_artifact
from decision_agent.modules.architectures.proposal_validation import validate_architecture_proposal
from decision_agent.shared.providers.base import LLMProvider


def build_mock_proposal(run: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    artifact = build_planning_artifact(run, root or Path.cwd())
    return artifact_to_proposal(artifact, run)


def propose_architecture(run: dict[str, Any], provider: LLMProvider, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact = build_planning_artifact(run, root, provider=provider)
    proposal = artifact_to_proposal(artifact, run)
    return artifact, proposal


__all__ = [
    "artifact_to_proposal",
    "build_mock_proposal",
    "build_planning_artifact",
    "propose_architecture",
    "validate_architecture_proposal",
]
