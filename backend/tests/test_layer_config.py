from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.governance.layer_config import (
    LayerConfig,
    get_layer_config,
)
from decision_agent.modules.runs.service import create_run


class TestLayerConfigDataclass(unittest.TestCase):
    def test_full_has_every_layer_on(self) -> None:
        cfg = LayerConfig.full()
        self.assertTrue(cfg.dsc_enabled)
        self.assertTrue(cfg.paap_enabled)
        self.assertTrue(cfg.dar_enabled)
        self.assertTrue(cfg.human_gate_enabled)
        self.assertTrue(cfg.contract_validators_enabled)

    def test_baseline_has_every_layer_off(self) -> None:
        cfg = LayerConfig.baseline()
        self.assertFalse(cfg.dsc_enabled)
        self.assertFalse(cfg.paap_enabled)
        self.assertFalse(cfg.dar_enabled)
        self.assertFalse(cfg.human_gate_enabled)
        self.assertFalse(cfg.contract_validators_enabled)

    def test_from_dict_round_trip(self) -> None:
        original = LayerConfig(dsc_enabled=True, paap_enabled=False, dar_enabled=True)
        restored = LayerConfig.from_dict(original.to_dict())
        self.assertEqual(original, restored)

    def test_from_dict_drops_unknown_keys(self) -> None:
        cfg = LayerConfig.from_dict({"dsc_enabled": False, "unknown_key": True})
        self.assertFalse(cfg.dsc_enabled)
        self.assertTrue(cfg.paap_enabled)  # default

    def test_from_dict_none_returns_full(self) -> None:
        self.assertEqual(LayerConfig.from_dict(None), LayerConfig.full())


class TestLayerConfigPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_run_persists_full_layer_config_by_default(self) -> None:
        run = create_run(
            {"task_id": "t1", "title": "Procure laptops", "description": "Buy 100 laptops"},
            self.root,
        )
        record = json.loads(
            (self.root / "data" / "runs" / run["run_id"] / "run-record.json").read_text("utf-8")
        )
        self.assertEqual(record["layer_config"], LayerConfig.full().to_dict())

    def test_create_run_persists_baseline_when_passed(self) -> None:
        run = create_run(
            {"task_id": "t1", "title": "Procure laptops", "description": "Buy 100 laptops"},
            self.root,
            layer_config=LayerConfig.baseline(),
        )
        loaded = get_layer_config(run["run_id"], self.root)
        self.assertEqual(loaded, LayerConfig.baseline())

    def test_create_run_accepts_dict_layer_config(self) -> None:
        run = create_run(
            {"task_id": "t1", "title": "Procure laptops", "description": "Buy 100 laptops"},
            self.root,
            layer_config={"dsc_enabled": False, "paap_enabled": True},
        )
        loaded = get_layer_config(run["run_id"], self.root)
        self.assertFalse(loaded.dsc_enabled)
        self.assertTrue(loaded.paap_enabled)

    def test_get_layer_config_missing_run_returns_full(self) -> None:
        cfg = get_layer_config("does_not_exist", self.root)
        self.assertEqual(cfg, LayerConfig.full())

    def test_create_run_persists_provider_override_and_benchmark_mode(self) -> None:
        run = create_run(
            {"task_id": "t1", "title": "Procure laptops", "description": "Buy 100 laptops"},
            self.root,
            provider_override="ollama/qwen2.5",
            benchmark_mode=True,
        )
        record = json.loads(
            (self.root / "data" / "runs" / run["run_id"] / "run-record.json").read_text("utf-8")
        )
        self.assertEqual(record["provider_override"], "ollama/qwen2.5")
        self.assertTrue(record["benchmark_mode"])


if __name__ == "__main__":
    unittest.main()
