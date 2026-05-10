# Architecture Principles and Tradeoffs — Governed Decision Agent

Date: 2026-05-09
Source: empirical observation from ablation benchmark + design analysis
Context: procurement domain, 5-worker funnel, claude-sonnet-4-6, conditions A0/A/C/F

---

## 1. Token composition and real cost

A procurement run (5 workers, full governed stack) produces approximately:

| Component | Count | Share |
|---|---|---|
| Input tokens | ~195,000 | ~91% |
| Output tokens | ~18,000 | ~9% |
| Ratio | 10:1 | — |

The input dominates because it carries the system prompt, knowledge files, tool results,
prior worker outputs, DB rows from the SQL connector, and governance rules. The model
generates a fraction of what it reads.

**At Anthropic Sonnet 4.6 pricing ($3/MTok input, $15/MTok output):**
- A-condition run (architecture, no governance): ~$0.85
- F-condition run (full governed stack): ~$0.86
- Governance overhead in tokens: ~$0.01 per run — negligible

The cost difference between conditions is not in money but in time and reliability.

---

## 2. Execution time breakdown

Per-worker wall times for a procurement run (claude-sonnet-4-6):

| Worker | Role | Time |
|---|---|---|
| requirement_analyst | Extract structure from task | 38–49 s |
| market_scout | Research supply market | 46–56 s |
| risk_assessor | Rate procurement risks | 76–93 s |
| evaluator | Score and shortlist vendors | 71–174 s |
| recommender | Produce decision brief | 65–97 s |

Intake workers (requirement_analyst, market_scout, risk_assessor) run in parallel.
Evaluator and recommender are serial (dependency graph).

- A0 (single call, no workers): ~1 min
- A/C/F (5 workers, parallel intake): ~4–5 min elapsed

The harness costs 3–4 extra minutes for a 5-worker procurement run. This overhead is
justified only when the inputs are complex and the decision is consequential (see section 5).

---

## 3. The LLM vs numerical task boundary

This is the most important architectural principle and the most commonly violated one.

**Rule: LLMs interpret. Code computes.**

| LLM job | Numerical / code job |
|---|---|
| Understand context and intent | Read database rows (exactly) |
| Write prose and reasoning | Score evidence (deterministic formula) |
| Extract structure from unstructured text | Apply threshold (boolean) |
| Generate recommendations and questions | Enforce budget ceiling |
| Identify gaps and surface uncertainties | Calculate salary, deductions, dates |
| Reason across multiple sources | Check compliance rule (yes/no) |

**Why this boundary is non-negotiable:**

If 200 employees receive salary, and the LLM rounds a deduction 1 EUR incorrectly,
that is 200 unhappy employees. If a production schedule shows 1 hour as free when it
is not, that hour is lost. These are not acceptable error modes for probabilistic models.

**Implementation:** the schema mapper in the ingestion layer enforces this. When a worker
calls `query_sql("payroll.salaries")`, the tool provider:
1. Reads the exact row from the database — no LLM involved
2. Annotates it with evidence_class="approved_spec" and authority=0.95
3. Passes only the excerpt string to the LLM for reasoning

The LLM sees: `{"type": "salary_record", "excerpt": "Employee X: EUR 3,200/month"}`.
It uses this for reasoning. It never handles the number for computation.

The PAAP scoring formula (authority × temporal × conflict × corroboration) is also
pure Python — no LLM in the path. The model proposes; deterministic code decides.

---

## 4. Smaller specialised models per worker

The current architecture runs all workers on the same model. A more efficient assignment
routes by task complexity:

| Worker | Task type | Recommended model | Cost reduction |
|---|---|---|---|
| requirement_analyst | Structured extraction | Haiku 4.5 | ~10× cheaper |
| market_scout | Retrieval + summarise | Haiku 4.5 | ~10× cheaper |
| risk_assessor | Classification + rating | Haiku 4.5 | ~10× cheaper |
| evaluator | Multi-source synthesis | Sonnet 4.6 | baseline |
| recommender | Final reasoning + brief | Sonnet 4.6 or Opus | same/higher |

Routing intake workers to Haiku would cut run cost by ~60% and speed by ~50%.
The evaluator and recommender do the load-bearing synthesis — those need a stronger model.

This is supported by the existing provider seam: each worker contract can carry a
`provider_override` field. The governance kernel (DSC, PAAP, DAR) is model-agnostic —
swapping the model beneath a worker does not change the governance outcome.

---

## 5. Memory architecture — retrieval when necessary, not always

### The retrieval decision

Memory retrieval has overhead. The architecture should not retrieve by default.
The gateway classifies query complexity first:

```
query → complexity classifier (fast small model)
              ↓
    simple:   direct answer — no retrieval
    medium:   knowledge base only — static files
    complex:  full memory + DSC scope + PAAP scoring + DAR + human gate
```

**Simple (no retrieval needed):**
- "Compare these two prices" — arithmetic
- "Is this vendor in our approved list?" — single DB lookup, no LLM
- "Summarise this document" — direct model call on the document

**Complex (retrieval and governance required):**
- "Recommend a vendor" — needs past decisions, risk register, market benchmarks, contracts
- "Review this engineering change" — needs original spec, prior reviews, regulatory constraints, dependency map
- "Should we hire this candidate?" — needs job spec, past hiring decisions, salary benchmarks, legal constraints
- "Approve this purchase order" — needs budget approval, supplier contract, compliance rules

The principle: **trigger retrieval at the decision boundary, not at every query.**
Retrieval is scoped to the current decision type (DSC) — a procurement run cannot retrieve
HR domain evidence even if the memory contains it.

### Obsidian as the human-editable memory layer

Obsidian (markdown knowledge graph with backlinks) maps directly to the architecture's
knowledge memory tier:

```
Obsidian vault
  └── decisions/
        └── 2024-08-15_lenovo_laptops.md     ← past decision, traceable
  └── vendors/
        └── lenovo.md                         ← vendor profile, human-curated
  └── compliance/
        └── gdpr_requirements.md              ← policy rules
  └── risks/
        └── risk-register.md                  ← risk patterns from past runs
```

Workers access these via `read_file` tool (respects DSC `allowed_read_paths`).
Backlinks in Obsidian become evidence citations — a note "Vendor: Lenovo → approved 2024"
is a queryable evidence record with provenance when indexed via the memory provider.

The human edits Obsidian. The architecture reads it. Neither overwrites the other.
Inferred preferences and learned patterns go into the memory provider; authoritative
rules and past decisions go into Obsidian — explicit, human-controlled, auditable.

---

## 6. When the harness is required — the decision matrix

```
Decision            Consequence  Inputs                     Use
──────────────────  ──────────── ─────────────────────────  ─────────────────────────
Single DB lookup    Low          1 record                   Code only. No LLM.
Simple comparison   Low          2–3 known values           Direct model call, no harness
Vendor selection    High         Contracts + law + specs    Full harness: DSC+PAAP+DAR
                                 + past decisions           + human gate + audit trail
Engineering review  Very high    Drawings + regulations +   Full harness + image models
                                 change history + images    + specialist worker per domain
Salary calculation  High (legal) Payroll table              Code only. Never LLM.
Hiring decision     High (legal) CV + spec + law            Harness with DSC blocking
                                 + past decisions           protected-class inference
Compliance check    High (legal) Regulation text            Harness with deterministic
                                 + internal policy          rule engine, not LLM judgment
```

**The harness earns its overhead when:**
1. Inputs span multiple sources (DB + documents + past decisions + images)
2. Output is consequential (money, legal commitment, personnel, safety)
3. Audit trail is required (who decided what, on what evidence, when)
4. Scope must be enforced (certain evidence or data is forbidden for this decision type)
5. Human must remain in the loop before final action

**The harness costs more than it earns when:**
1. Single source, single question
2. No legal or financial consequence
3. No replay or audit requirement
4. Speed is the primary requirement

---

## 7. The compliance-coverage tradeoff (from experimental results)

Tighter governance reduces task completion. This is not a failure — it is governance working.

From the frontier experiment (PAAP threshold sweep, procurement domain):

| Governance strictness | Coverage (completion) | Compliance (violations) |
|---|---|---|
| None (A0 baseline) | 90% | 6.3 violations/run |
| Governed, threshold 0.30 | 50% | 0.0 violations |
| Governed, threshold 0.60 | 60% | 0.0 violations |
| Governed, threshold 0.80 | 40% | 0.0 violations |
| Governed, threshold 0.95 | 0% | 0.0 violations |

At maximum strictness (0.95), the system refuses to act entirely. This is the correct
behaviour when evidence quality is insufficient for a high-stakes decision. The system
should not fabricate confidence.

**The operating principle:** governance is a tunable control layer. The threshold is a
business decision about risk tolerance, not a technical parameter. A 60% completion rate
with zero violations may be precisely right for a high-stakes procurement. A 90%
completion rate with 6 violations per run is wrong regardless of speed.

---

## 8. Summary of architectural rules derived from experiments

1. **LLM interprets; code computes.** Never route a number through an LLM if it must be exact.

2. **Governance is deterministic.** DSC scope, PAAP scoring, DAR authorization — no model call in any of these paths. Same inputs always produce the same governance outcome.

3. **Authority is assigned at ingestion, not at inference.** The schema mapper stamps evidence with authority before the LLM sees it. The LLM cannot upgrade its own evidence quality.

4. **Smaller models for structured tasks.** Intake workers doing extraction and classification do not need the same model as the evaluator doing multi-source synthesis.

5. **Memory is scoped, not global.** A worker retrieves only evidence within the current decision's DSC boundary. Cross-domain retrieval is structurally blocked, not just prompted away.

6. **Retrieval is triggered by complexity, not by default.** The gateway classifies before retrieving. Simple questions get direct answers. Complex decisions get the full pipeline.

7. **Coverage is a metric, not just completion.** A run that refuses to complete because evidence is insufficient is preferable to one that completes with fabricated evidence.

8. **The human gate is architectural, not advisory.** Final actions that are irreversible or external require a human approval event in the audit log. No architectural path bypasses this.
