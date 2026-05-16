from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from decision_agent.modules.governance.layer_config import LayerConfig

_FULL_CONDITION_MAP: dict[str, tuple[LayerConfig, str | None]] = {
    "A0":      (LayerConfig.baseline(), "anthropic"),
    "A0_inf":  (LayerConfig.baseline(), "anthropic"),
    "A":       (LayerConfig.baseline(), None),
    "C":       (LayerConfig(dsc_enabled=False, paap_enabled=False, dar_enabled=False,
                            human_gate_enabled=False, contract_validators_enabled=True), "anthropic"),
    "F":       (LayerConfig.full(),     "anthropic"),
    "G_qwen":  (LayerConfig.full(),     "ollama/qwen2.5"),
    "G_llama": (LayerConfig.full(),     "ollama/llama3.1"),
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

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def list_fixtures() -> list[str]:
    return sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Benchmark fixture not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))
