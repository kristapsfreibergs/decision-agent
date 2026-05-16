# Benchmark Configs

**Single run (one rep, one condition):**

```bash
PYTHONPATH=backend/src python -m decision_agent.cli benchmark-config configs/benchmarks/frontier-baseline.json
```

To run just one rep, temporarily set `"reps": 1` in the config before running.

**Run any config:**

```bash
PYTHONPATH=backend/src python -m decision_agent.cli benchmark-config configs/benchmarks/<name>.json
```

Results land in `data/benchmarks/<benchmark_id>/` as `results.csv` + `summary.json`.

---

## Architecture ablation (primary thesis experiment)

Same procurement task across governance conditions — proves architecture, not the
model, enforces the rules.

| Config | Conditions | Fixtures | Reps |
|---|---|---|---|
| `procurement-layer-ablation.json` | A0, A, C, F | laptops | 3 |
| `procurement-compliance-coverage.json` | A0, A, C, F | laptops + consulting | 5 |

**Conditions:**
- `A0` — single LLM call, no architecture, no governance (true baseline)
- `A`  — architecture + contracts, all governance layers OFF
- `C`  — architecture + validators ON, DSC/PAAP/DAR OFF
- `F`  — full governed stack (DSC + PAAP + DAR + human gate)
- `G_qwen` / `G_llama` — full stack with Ollama local models

---

## Compliance-coverage frontier (PDF paper replication)

Sweeps governance strictness (`paap_min_avg_score`) to produce the
compliance–coverage curve. Run all five in sequence, then plot:

- x-axis: `run_completed` (coverage)
- y-axis: `scope_violations == 0` or `unsafe_approvals == 0` (compliance)
- one data point per config

The governed curve should sit above-left of the flat A0 baseline — better
compliance at comparable or lower coverage, and zero unsafe approvals.

| Config | `paap_min_avg_score` | Coverage (expected) | Compliance (expected) |
|---|---|---|---|
| `frontier-baseline.json` | none (A0) | high | low — baseline violations |
| `frontier-governed-low.json` | 0.30 | high | good |
| `frontier-governed-mid.json` | 0.60 | moderate | high (default operating point) |
| `frontier-governed-high.json` | 0.80 | lower | very high |
| `frontier-governed-max.json` | 0.95 | very low | near-perfect |

The mid config is the same operating point as the main ablation `F` condition.
Re-run it here only for a consistent rep count across the frontier dataset.

**Thesis statement reproduced from PDF:**
> Governance is a tunable control layer that shifts the safety/completion
> operating point — not a free improvement.

---

## Config schema

```json
{
  "name": "string — used in benchmark_id slug",
  "description": "string — documentation only",
  "conditions": ["A0", "A", "C", "F"],
  "fixtures": ["procurement_laptops"],
  "reps": 3,
  "timeout_seconds": 600,
  "paap_min_avg_score": 0.6
}
```

`paap_min_avg_score` overrides `EVIDENCE_PROFILE["min_avg_score"]` in every
generated contract for that run. Only governed conditions (F, G_*) are
affected — A0/A/C ignore it since their PAAP layer is off.
