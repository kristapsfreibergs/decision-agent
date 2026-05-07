from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LayerConfig:
    """Toggleable governance layers for a run.

    Stored in run-record.json["layer_config"]. Each governance entry function
    reads it once via get_layer_config(run_id, root) and threads needed flags
    down. No module-level singleton: parallel benchmark runs need per-run state.
    """

    dsc_enabled: bool = True
    paap_enabled: bool = True
    dar_enabled: bool = True
    human_gate_enabled: bool = True
    contract_validators_enabled: bool = True

    @classmethod
    def baseline(cls) -> "LayerConfig":
        """Condition A: prompt-only baseline. All governance OFF."""
        return cls(
            dsc_enabled=False,
            paap_enabled=False,
            dar_enabled=False,
            human_gate_enabled=False,
            contract_validators_enabled=False,
        )

    @classmethod
    def full(cls) -> "LayerConfig":
        """Conditions F and G: full governed stack. All ON."""
        return cls()

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "LayerConfig":
        if not value:
            return cls.full()
        known = {f.name for f in fields(cls)}
        filtered = {k: bool(v) for k, v in value.items() if k in known}
        return cls(**filtered)

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


def get_layer_config(run_id: str, root: Path) -> LayerConfig:
    """Load LayerConfig from a run's run-record.json. Defaults to full() if absent."""
    record_path = root / "data" / "runs" / run_id / "run-record.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return LayerConfig.full()
    return LayerConfig.from_dict(record.get("layer_config"))
