from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_agent.modules.evaluation.config_runner import load_benchmark_config


class BenchmarkConfigTest(unittest.TestCase):
    def test_loads_repository_config(self) -> None:
        cfg = load_benchmark_config(
            Path("configs/benchmarks/procurement-layer-ablation.json")
        )
        self.assertEqual(cfg.name, "procurement_layer_ablation")
        self.assertEqual(cfg.conditions, ["A0", "A", "C", "F"])
        self.assertEqual(cfg.fixtures, ["procurement_laptops"])
        self.assertEqual(cfg.reps, 3)

    def test_rejects_unknown_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "conditions": ["NOPE"],
                        "fixtures": ["procurement_laptops"],
                        "reps": 1,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unknown benchmark conditions"):
                load_benchmark_config(path)


if __name__ == "__main__":
    unittest.main()
