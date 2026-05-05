from __future__ import annotations

from copy import deepcopy
from typing import Any

from decision_agent.modules.architectures.software_scaffold_build import SOFTWARE_SCAFFOLD_BUILD

_ARCHITECTURES = [SOFTWARE_SCAFFOLD_BUILD]


def list_architectures() -> list[dict[str, Any]]:
    return deepcopy(_ARCHITECTURES)


def find_architecture_for_decision(decision_type: str) -> dict[str, Any] | None:
    for architecture in _ARCHITECTURES:
        if architecture["decision_type"] == decision_type:
            return deepcopy(architecture)
    return None

