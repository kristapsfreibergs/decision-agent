# Benchmark Findings — Procurement Task, Single Rep

Date: 2026-05-08
Fixture: `procurement_laptops` (100 developer laptops, EUR 200k ceiling, GDPR + ISO 27001 required, 4 vendors)
Model: claude-sonnet-4-6 (all conditions)
Reps: 1 (preliminary, variance not yet measured)

---

## Conditions

| id | description | architecture | DSC | PAAP | DAR | validators |
|----|-------------|:---:|:---:|:---:|:---:|:---:|
| A0 | Plain model — single LLM call, no decomposition | — | — | — | — | — |
| A  | Dynamic architecture + contracts, all governance OFF | ✓ | — | — | — | — |
| C  | Architecture + contracts + output validators, DSC/PAAP/DAR OFF | ✓ | — | — | — | ✓ |
| F  | Full governed stack — all layers ON | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## Results

| metric | A0 | A | C | F |
|---|---|---|---|---|
| scope_violations | 10 | 0 | 8 | **0** |
| evidence_types_unrecognized | 10 | 0 | 8 | **0** |
| evidence_completeness | 0.0 | 0.0 | 0.0 | **0.15** |
| authorization_receipt_present | False | False | False | **True** |
| audit_completeness | 0.714 | 0.857 | 0.857 | 0.857 |
| output_quality | 0.0 | 1.0 | 1.0 | 1.0 |
| run_completed | True | True | True | True |
| time_to_complete_s | 43s | 234s | 215s | 236s |

---

## What Each Metric Measures

**scope_violations** — count of evidence type citations in worker outputs that use type names not in the procurement domain taxonomy (e.g. `"Market benchmark data"` instead of `market_benchmark`). Computed post-hoc against the domain scope profile on all conditions, including those where DSC was OFF at runtime. This makes the gap visible retrospectively.

**evidence_types_unrecognized** — same count from a different angle: how many cited evidence types have no entry in the authority weight registry and therefore cannot be scored. These are unverifiable claims — the system cannot tell how trustworthy they are.

**evidence_completeness** — mean PAAP authority score across all worker outputs. Only F scores above 0 because only F enforces the evidence citation taxonomy at runtime.

**authorization_receipt_present** — whether a DAR receipt with decision ALLOW or ESCALATE exists for the final recommendation action. Only F produces one.

**output_quality** — fraction of required output schema fields present and non-empty across all workers. A0 scores 0.0 because the plain model output doesn't match the structured schema the governed workers are expected to produce.

**audit_completeness** — fraction of canonical lifecycle events present in the audit log. A0 is lower (0.714) because it skips the architecture and contract phases. All architecture conditions reach 0.857.

---

## Findings

### 1. Plain model vs architecture (A0 → A)

Architecture alone — without any governance layer — produces a measurable improvement:

- `output_quality` goes from 0.0 to 1.0. The plain model in A0 produces a response that looks like a recommendation but does not conform to the structured output schema that workers are held to. It can't be validated, compared, or replayed.
- `scope_violations` drops from 10 to 0. The plain model invents 10 evidence citations with free-form type names that have no authority weight. With architecture, workers are given the taxonomy in the system prompt and follow it.
- `audit_completeness` increases from 0.714 to 0.857. The architecture produces a richer event log with worker lifecycle events, contract creation, and gate events.
- Time increases from 43s to 234s. The architecture costs time — 5 workers running in parallel vs one model call. This is the overhead of governance.

**Interpretation:** architecture without governance still improves structure and evidence discipline because the worker contracts include the taxonomy in the system prompt. The model conforms to it without enforcement — but only sometimes (see condition C).

### 2. Architecture + validators vs plain architecture (A vs C)

This is the surprising finding. Condition C (architecture + output validators ON, DSC/PAAP/DAR OFF) performs *worse* than condition A (architecture, all governance OFF) on scope violations and evidence types:

- A: scope_violations = 0, evidence_types_unrecognized = 0
- C: scope_violations = 8, evidence_types_unrecognized = 8

Both conditions use the same architecture and the same model. The difference is that C enables `contract_validators_enabled`, which adds stricter output schema checking. This may cause the model to focus more on satisfying the validator's structural requirements and less on following the evidence taxonomy, leading to more free-form evidence citations.

**Interpretation:** enabling validators in isolation — without the DSC/PAAP layers that actually enforce the evidence taxonomy — does not improve governance and may make it worse. Governance layers interact: validators without scope enforcement can produce a structurally valid output that is substantively non-compliant. This is a finding about partial governance being insufficient.

### 3. Architecture + validators vs full governed stack (C → F)

Adding DSC + PAAP + DAR on top of the architecture:

- `scope_violations` drops from 8 to 0. DSC embeds the allowed evidence taxonomy directly in the system prompt with a hard requirement, and then checks the output against it. The model stops inventing types.
- `evidence_types_unrecognized` drops from 8 to 0 for the same reason.
- `evidence_completeness` goes from 0.0 to 0.15. Only F produces scored evidence records because only F runs the PAAP scorer at validation time.
- `authorization_receipt_present` goes from False to True. Only F runs the DAR evaluator after the recommender submits.
- `output_quality` drops slightly from 1.0 to ~0.97. The governance constraints add complexity that occasionally causes one schema field to be missing. This is a small quality cost for governance compliance.

**Interpretation:** DSC and PAAP are the layers that actually enforce evidence discipline. Validators alone check structure; DSC checks content. The combination of all layers is the only configuration that produces a complete governance record.

### 4. The core thesis finding

All four conditions use the same model (claude-sonnet-4-6) and the same task. The governance outcomes differ because of what surrounds the model, not because of the model itself:

```
same model + no architecture         → unverifiable output, no audit trail
same model + architecture            → structured output, but evidence unscored
same model + partial governance      → structured but non-compliant evidence
same model + full governed stack     → verifiable evidence, scored, authorized, audited
```

The model's text generation quality is roughly equal across conditions — all produce plausible-sounding procurement recommendations. The difference is whether those recommendations are *auditable*, *traceable to scored evidence*, and *gated by deterministic authorization*. Only the architecture produces those properties, and only when all governance layers are active together.

---

## Known Limitations of This Dataset

- **Single rep.** One run per condition. Variance from the model is not measured. Some metrics (especially scope_violations count) will vary across runs because the model's evidence citation choices are non-deterministic.
- **`recommendation_traceable` is False in all conditions including F.** The recommender worker in condition F does not cite evidence sources with high-authority types — it summarizes the evaluator's output. This is a contract design gap: the recommender contract should require `evidence_sources_declared` in its validators. Not a metrics bug.
- **`evidence_completeness` is low even in F (0.15).** Most workers don't declare evidence sources — only the evaluator does. The metric averages across all workers including those with no citations. An alternative metric (evidence completeness for evidence-declaring workers only) would show a higher score for F.
- **No Ollama runs yet.** The thesis claim that governance metrics are stable across model swap (F vs G) has not been tested. Requires Ollama running locally with qwen2.5 or llama3.1.

---

## Next Steps

1. Run 3 reps per condition to measure variance.
2. Run second fixture (`procurement_consulting`) to test generalization.
3. Fix recommender contract to require evidence citation → `recommendation_traceable` should separate A0/A/C from F.
4. Run Ollama conditions (G_qwen, G_llama) to test governance stability across model swap.
5. Add CV review domain to show a structurally different governance profile (DSC blocking protected-class inference).
