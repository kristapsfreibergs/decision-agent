from __future__ import annotations

import os
from typing import Any

from decision_agent.modules.governance.layer_config import LayerConfig

_FULL_CONDITION_MAP: dict[str, tuple[LayerConfig, str | None]] = {
    "A0": (LayerConfig.baseline(), None),
    "C":  (LayerConfig(dsc_enabled=False, paap_enabled=False, dar_enabled=False,
                       human_gate_enabled=False, contract_validators_enabled=True), None),
    "F":  (LayerConfig(dsc_enabled=True, paap_enabled=True, dar_enabled=True,
                       human_gate_enabled=False, contract_validators_enabled=True), None),
}


def _active_conditions() -> dict[str, tuple[LayerConfig, str | None]]:
    raw = os.environ.get("BENCHMARK_PROVIDERS", "").strip()
    if not raw:
        return dict(_FULL_CONDITION_MAP)
    allowed = {p.strip().lower() for p in raw.split(",") if p.strip()}
    filtered: dict[str, tuple[LayerConfig, str | None]] = {}
    for name, (cfg, provider) in _FULL_CONDITION_MAP.items():
        if provider is None or provider.lower() in allowed:
            filtered[name] = (cfg, provider)
    return filtered or dict(_FULL_CONDITION_MAP)


class _ConditionMapView:
    def __iter__(self):
        return iter(_active_conditions())

    def __getitem__(self, key):
        return _active_conditions()[key]

    def __contains__(self, key):
        return key in _active_conditions()

    def keys(self):
        return _active_conditions().keys()

    def items(self):
        return _active_conditions().items()

    def get(self, key, default=None):
        return _active_conditions().get(key, default)


CONDITION_MAP: Any = _ConditionMapView()


def list_fixtures() -> list[str]:
    """List available case studies (delegates to case_study module)."""
    from decision_agent.modules.evaluation.case_study import list_case_studies
    return list_case_studies()


def load_fixture(name: str) -> dict[str, Any]:
    """Load a case study task definition (delegates to case_study module)."""
    from decision_agent.modules.evaluation.case_study import load_case
    return load_case(name)
