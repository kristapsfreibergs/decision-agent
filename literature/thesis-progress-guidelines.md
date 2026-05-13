# Thesis Progress Guidelines
# Architecture of LLM-Based Organizational Information Systems
# Author: Kristaps Freibergs (Kuzņecovs), University of Latvia

---

## Argument Progression (one line per step)

1. LLMs are being used for high-stakes decisions but are probabilistic — this is architecturally wrong.
2. No individual component (RAG, memory, fine-tuning, guardrails) fixes this — each introduces its own loss.
3. Combining components compounds the losses — there is no emergent correctness from stacking imprecise parts.
4. A better model does not solve it — the problem is categorical, not a matter of scale.
5. Language encodes the surface form of decisions, not the institutional process that makes them binding.
6. The minimum necessary architecture requires three explicit layers: scope (DSC), evidence authority (PAAP), and deterministic authorization (DAR).
7. Governance must be injected at generation time inside the worker, not applied as a post-execution filter — Condition C vs F proves this.
8. The empirical benchmark shows: same model, four conditions, only the full governed stack produces zero violations, scored evidence, and an authorization receipt.
9. Governance is a tunable tradeoff — tighter thresholds reduce coverage, not compliance — and the operating point can be chosen on the frontier.
10. Different decision types require different agent compositions — the system selects topology based on decision type, then injects governance parameters per domain.
11. The same structural pattern can run across multiple domains by separating agent structure from governance parameters — structure is fixed, domain parameters are injected.

---

## 1. Project Overview

This is a Computer Science Master's Thesis at the University of Latvia (DatZM009).

**Title:** Architecture of LLM-Based Organizational Information Systems
**Supervisor:** Dr.sc.comp., asoc. prof. Ivo Oditis
**Programme Director:** Dr.math., prof. Karlis Podnieks

**Implementation:** The `decision-agent` repository is the working prototype that validates
the theoretical architecture. Code and thesis are coherent — the implementation *is* the
empirical artifact that answers the research questions.

---

## 2. Core Thesis Argument

The thesis makes a single, falsifiable, empirically supported claim:

> No improvement to any individual component — better retrieval, better model, better
> prompting, better memory — is sufficient for high-stakes industrial use without a
> deterministic authorization layer. The layer is not an enhancement. It is a prerequisite.

This argument proceeds in three steps:

1. **Combinatorial insufficiency** — each component introduces its own information loss or
   uncertainty. Combining them does not cancel losses, it compounds them.
2. **The perfect model myth** — scaling alone cannot solve governance problems because the
   problem is categorical, not quantitative. Better model = still probabilistic = still
   cannot guarantee auditability, determinism, or normative compliance.
3. **Deterministic authorization as prerequisite** — the governance layer must be the
   architectural foundation from which other components operate within defined, auditable
   boundaries.

---

## 3. Why LLMs Cannot Do Deterministic Tasks Alone

### The standard critique
LLMs are probabilistic reasoners being forced into roles requiring deterministic, auditable,
repeatable behavior — which is architecturally wrong:
- Same input → different output (non-deterministic)
- No formal guarantees on correctness
- Hallucination in high-stakes decisions
- No traceable reasoning chain that can be audited or challenged
- Cannot be formally verified or tested exhaustively
- Confidence does not correlate with correctness

### The deeper argument: combinatorial insufficiency of components

Each component individually introduces its own information loss:

- **RAG / k-top retrieval** — retrieves semantically similar, not normatively relevant.
  Everything outside top-k is lost. You cannot know what you lost.
- **Vector DB** — embeds meaning into latent space that collapses distinctions. Two legally
  different documents can be neighbors. Two identical legal facts from different authorities
  get equal weight.
- **Fine-tuning** — bakes knowledge into weights, making it unauditable and unverifiable.
  You cannot trace which training example produced a specific output.
- **Guardrails** — check output after generation. The reasoning is already done. You are
  filtering, not governing.
- **Memory** — degrades over time, mixes high and low authority sources, has no expiry or
  source weighting mechanism.
- **Longer context** — Liu et al. showed performance degrades for information in the middle.
  More context is not guaranteed access.

**The key insight:** combining these components does not cancel out their losses — it
compounds them. Each layer introduces its own failure mode. The combined system has all of
them simultaneously. There is no emergent correctness from stacking imprecise components.

This is validated empirically: Condition C (architecture + validators) is *worse* than
Condition A (architecture alone) on scope violations — partial governance can regress.

### Why the "better model" argument fails

The "perfect model myth": the assumption that governance problems are transient and will be
solved by better models.

This fails because it confuses two distinct things:
- **Semantic inference quality** — what the model can be improved at
- **Normatively binding decision governance** — what the model structurally cannot provide

Even a perfect model cannot satisfy:
- **Reproducibility** — probabilistic sampling breaks this categorically
- **Authority traceability** — sources are collapsed into latent representations, the chain
  is lost
- **Normative compliance** — rules exist *outside* the model (law, procurement threshold,
  ISO requirement). The model approximates the rule, it does not execute it.
- **Time horizon** — a 20-year consequence decision requires a durable institutional record.
  A model output is not one.
- **Contestability** — in a court, every reasoning step must be challengeable. A model's
  internal process is not externally inspectable.

**The deepest point:** Language encodes the *surface form* of decisions — the words humans
use when they have already decided. It does not encode the *institutional process* by which
decisions become binding. A judge's ruling is not binding because it is linguistically
coherent. It is binding because of the institutional chain: jurisdiction, procedure,
evidence rules, signature, appeal process. None of that lives in language.

### The precise thesis statement

> LLMs can approximate the semantic content of decisions. They cannot instantiate the
> institutional process that makes a decision legitimate, binding, auditable, and
> contestable. That process requires an architectural layer external to the model —
> deterministic, traceable, and governed by rules that exist independently of any training
> distribution.

This is not a temporary limitation. It is a categorical distinction between language
and institution.

### Alternatives being researched (future directions)

- Hybrid systems — LLM as planner, deterministic engine as executor (this thesis)
- Formal methods + LLM (LLM generates formal specs, model checker verifies)
- Retrieval + structured reasoning (RLM) — closer to what PAAP/DSC enforce
- Neuro-symbolic systems — neural pattern matching + symbolic logic engines
- Decision trees / constraint solvers for deterministic parts
- Process calculi / workflow engines with LLMs filling bounded slots

---

## 4. Thesis Research Story

**Progression:**

1. Established the governance gap in LLM-based systems
2. Analyzed comprehensive architecture needed for enterprise information systems
3. Identified the minimum necessary architecture for autonomous high-stakes decisions
4. Formalized three novel governance constructs: DSC, PAAP, DAR
5. Built a working prototype (decision-agent) implementing the architecture
6. Ran empirical benchmarks across multiple models and scenarios
7. Documented results for determinism and repeatability

**Three empirical scenarios:**
- CV comparison (candidate screening)
- Procurement organization (vendor selection)
- Pricing offers (construction/procurement)

**Model range tested:** frontier models (claude-sonnet-4-6) down to simpler models,
documenting determinism and repeatability results.

**Remaining gap:** Cross-model runs (Ollama/qwen2.5/llama3.1) not yet completed — the
claim that governance metrics are stable across model swap is the most important remaining
experiment.

---

## 5. The Three Novel Governance Constructs

### DSC — Decision Scope Contract
Defines what evidence is in bounds, what is out of scope. Embeds allowed evidence taxonomy
directly in the system prompt with hard requirements, then checks worker outputs against it.

Effect demonstrated: scope_violations drop from 6.3 (baseline) to 0.0 (all governed
conditions) — independent of PAAP threshold level.

### PAAP — Probabilistic Authority Assessment Protocol
Quantitatively scores evidence authority by source type:
- `architecture_doc`: 0.95
- `existing_code`: 0.90
- `vendor_proposal`: 0.90
- `user_request`: 0.85
- `generated_plan`: 0.45
- `model_inference`: 0.00 (forbidden as evidence)

Workers operating under PAAP must cite typed evidence sources. Model inference is
explicitly prohibited. Workers that cannot cite sufficient authority must refuse to
conclude and defer to human.

### DAR — Decision Authorization Record
Deterministic gate that issues ALLOW / ESCALATE / DENY receipts based on:
- Consequence class of the proposed action
- Evidence floor met (PAAP score vs threshold)
- Layer configuration

Only the full governed stack (F) produces DAR receipts. This is the authorization chain
that makes the decision auditable and contestable.

---

## 6. Empirical Benchmark Results

### Benchmark 1: Ablation Study (findings doc 1)

**Fixture:** procurement_laptops — 100 developer laptops, EUR 200k, GDPR + ISO 27001
**Model:** claude-sonnet-4-6 (all conditions)
**Reps:** 1 preliminary

| Condition | Description | scope_violations | evidence_completeness | DAR receipt | output_quality |
|---|---|---|---|---|---|
| A0 | Plain model, no architecture | 10 | 0.0 | False | 0.0 |
| A | Architecture + contracts, governance OFF | 0 | 0.0 | False | 1.0 |
| C | Architecture + validators, DSC/PAAP/DAR OFF | 8 | 0.0 | False | 1.0 |
| F | Full governed stack, all layers ON | 0 | 0.15 | True | 1.0 |

**Key finding:** Condition C (partial governance) is *worse* than A (no governance) on
scope violations. Validators without scope enforcement produce structurally valid but
substantively non-compliant output. Partial governance is insufficient and can regress.

**The four-line summary:**
```
same model + no architecture         → unverifiable output, no audit trail
same model + architecture            → structured output, but evidence unscored
same model + partial governance      → structured but non-compliant evidence
same model + full governed stack     → verifiable evidence, scored, authorized, audited
```

### Benchmark 2: Compliance-Coverage Frontier (findings doc 2)

**Fixtures:** procurement_laptops + procurement_consulting
**Reps:** 5 per condition per fixture = 50 total runs
**PAAP threshold sweep:** 0.30 / 0.60 / 0.80 / 0.95

| Condition | PAAP threshold | Coverage | Scope violations | DAR receipt |
|---|---|---|---|---|
| A0 baseline | none | 0.90 | 6.30 | 0.00 |
| F governed-low | 0.30 | 0.50 | 0.00 | 0.50 |
| F governed-mid | 0.60 | 0.60 | 0.00 | 0.60 |
| F governed-high | 0.80 | 0.40 | 0.00 | 0.40 |
| F governed-max | 0.95 | 0.00 | 0.00 | 0.00 |

**Key findings:**

1. Architecture eliminates scope violations at *every* threshold level — even 0.30.
   This is a DSC effect, not a PAAP threshold effect.
2. Tighter thresholds reduce coverage, not compliance. Compliance is constant at zero
   across all governed conditions.
3. At 0.95, zero runs completed — governance collapse reproduced (matches ICLR 2025
   paper Banking77/AG News findings).
4. Default operating point (0.60) achieves best observed balance: 0.6 coverage,
   0.0 violations, 0.6 DAR receipt rate.
5. Output quality preserved under governance (~0.99). Cost of governance is coverage
   (fewer completions), not quality (worse outputs when completed).
6. Time overhead: governed stack ~5x slower than plain model (236s vs 48.6s).

**The core contrast in outputs:**

A0 (plain model) produced a confident Lenovo recommendation with 8 fabricated evidence
sources — invented certificate numbers, invented IDC market share figures, invented pricing.
Scope violations: 10. Every evidence type unrecognized by taxonomy.

F governed-mid produced: no vendor named, 3 blocking gaps surfaced (OS spec missing, CPU
spec missing, budget owner sign-off missing), 10 traceable contract conditions, explicit
refusal to score because "model inference authority weight 0.00 — forbidden as evidence."

Same model. Same task. Architecture is the difference.

**Precise thesis statement supported by data:**

> Deterministic governance layers improve policy compliance in controlled procurement
> decision benchmarks. The full governed stack eliminates scope violations and produces
> auditable authorization receipts across all tested thresholds. Governance imposes a real
> coverage cost: stricter evidence requirements reduce task completion, and at maximum
> strictness the system refuses to act entirely. The value of governance should be evaluated
> on the compliance-coverage frontier, not at a single operating point. The default
> configuration (PAAP 0.60) achieves the best observed balance: 0.6 coverage with zero
> violations versus the baseline's 0.9 coverage with 6.3 violations per run.

---

## 7. What Is a Decision — Formal Definition

Before governing a decision, it must be formally defined.

**A decision is not a model output. A decision has:**
- **Subject** — what is being decided
- **Scope** — what evidence is in bounds, what is out
- **Authority conditions** — who or what can legitimately make this decision
- **Consequence class** — what happens if it is wrong (reversible vs irreversible)
- **Evidence requirements** — what must be known before deciding
- **Threshold** — when is enough evidence enough
- **Commitment point** — the moment it becomes binding

Different decision types have structurally different requirements:
- Pricing decision: market benchmarks + authority approval threshold
- CV screening: criteria + protected class exclusion rules
- Procurement: compliance verification + competition rules
- Financial approval: evidence floor + consequence class gate

These are not the same structure. The governance layer must be parameterized by decision
type — which is exactly what DSC, PAAP, and DAR do.

---

## 8. How the System Handles Different Decision Types

### How decision routing works in the prototype

The decision-agent prototype classifies the incoming task and selects a different agent
composition depending on what kind of decision is needed. Each composition has its own
set of agents, execution order, interaction pattern, and completion condition. The
governance layer (DSC, PAAP, DAR) is then applied on top of whichever composition was
selected, with parameters injected per domain.

For reference, each composition can be described as a tuple:

```
DAI(D) = (A, T, G, P, C)
```

Where:
- `A` = agents spawned for this decision type
- `T` = topology — execution order and structure
- `G` = governance parameters (DSC scope, PAAP weights, DAR rules) — injected per domain
- `P` = interaction pattern between agents
- `C` = completion condition — when the decision is considered closeable

### Two concrete implemented examples

**AutoResearchClaw — knowledge synthesis tasks**

The task being handled:
> "What is known about this topic, what gaps exist, and what hypothesis is worth testing?"

The system uses a 23-stage sequential pipeline where each agent passes a structured
artifact to the next. Stages narrow the information space toward a conclusion. No agent
contests another.

```
TOPIC_INIT → PROBLEM_DECOMPOSE → SEARCH_STRATEGY
→ LITERATURE_COLLECT → LITERATURE_SCREEN [gate]
→ KNOWLEDGE_EXTRACT → SYNTHESIS → HYPOTHESIS_GEN
→ EXPERIMENT_DESIGN [gate] → CODE_GENERATION
→ RESEARCH_DECISION (PROCEED / PIVOT / REFINE)
→ PAPER_DRAFT → PEER_REVIEW → PAPER_REVISION → QUALITY_GATE [gate]
→ EXPORT_PUBLISH → CITATION_VERIFY
```

When the RESEARCH_DECISION stage returns PIVOT or REFINE, the pipeline rolls back to an
earlier stage and re-executes from there. Completion requires a paper produced, citations
verified, and quality score meeting the threshold.

---

**AutoDebate — option selection tasks**

The task being handled:
> "Which of these options is better, and why, given contested evidence?"

The system uses an adversarial round structure. Two agents argue opposing positions.
An arbiter evaluates the arguments and applies the decision rules. The arbiter does not
generate a position — it rules on the contest.

```
PROPOSER (argues for option A)
    ↕ (structured rebuttal rounds)
CHALLENGER (argues against A / for B)
    ↓
ARBITER (evaluates arguments, applies decision rules)
    ↓
DECISION (with traceable reasoning)
```

Completion requires a ruling with a traceable argument chain and explicit record of which
arguments were accepted and which were rejected.

### Comparison of the two compositions

| Dimension | Knowledge synthesis | Option selection |
|---|---|---|
| Task type | Converge large information space | Contest competing claims |
| Topology | Sequential pipeline | Adversarial rounds |
| Agent relationship | Cooperative, additive | Adversarial, contesting |
| Interaction pattern | Accumulate and narrow | Argue and arbitrate |
| Evidence handling | Collected and weighted by authority | Presented and challenged by opponent |
| Human gate placement | At quality checkpoints | At final arbiter ruling |
| Rollback mechanism | PIVOT back to earlier stage | Additional debate round |
| Completion signal | Quality score ≥ threshold | Arbiter ruling with evidence trace |
| Output | Structured artifact (paper, plan) | Decision with argument chain |
| Failure mode | Weak evidence → low quality score | Insufficient evidence → no ruling possible |

The governance layer sits on top of both compositions. The structure changes per decision
type; the governance parameters change per domain. These are independent dimensions.

---

## 9. How the Same Agent Structure Can Be Used Across Domains

### The reuse problem

The same structural pattern — for example, comparing N options against M criteria — appears
in many domains: vendor selection, CV screening, medical treatment choice, court evidence
evaluation, academic peer review. The temptation is to reuse the same agent composition
across all of them.

This does not work directly, for a few reasons:

- The comparison structure looks the same but the authority weights are completely
  different per domain. `vendor_proposal` is authoritative in procurement and irrelevant
  in medicine. Reusing without changing the weights produces a structurally valid result
  that is normatively wrong for the domain.
- Evidence authority is domain-specific. What counts as a credible source differs.
- Completion conditions differ. Procurement comparison is done when evidence floor is met.
  A legal comparison is done when both sides have been heard. Same structure, different
  closing rules.
- Some domains have hard forbidden inferences — age in CV screening, character in court —
  that do not exist in other domains and cannot be carried over from a generic component.

### How the prototype handles this

The prototype separates structure from domain parameters. The agent topology — the sequence
of agents, how they interact, and how completion is detected — is defined once. The domain
parameters — evidence weights, forbidden inferences, required evidence classes, consequence
class, and authorization rules — are injected at run time via DSC, PAAP, and DAR.

This means the same structural pattern can be instantiated differently per domain without
rewriting the agent logic. The governance layer carries all the domain specificity.

### Example: the same `Multi-source Comparison` structure instantiated across 5 domains

Structure in all cases: Scope → Gather N sources → Score against criteria → Rank → Authorize

| Domain | Evidence authority (injected via PAAP) | Forbidden inferences (injected via DSC) | Gate |
|---|---|---|---|
| Vendor procurement | vendor_proposal=0.9, model_inference=0.0 | Unverified pricing | DAR ALLOW if evidence floor met |
| CV / candidate screening | official_certificate=0.95, self_reported=0.3 | Age, nationality, photo | Human review mandatory |
| Medical treatment selection | clinical_trial=0.95, case_report=0.5, model_inference=0.0 | Off-label inference without citation | Physician sign-off |
| Court evidence evaluation | primary_document=0.95, witness_testimony=0.7, hearsay=0.2 | Character inference | Judge ruling |
| Academic peer review | experimental_result=0.9, theoretical_claim=0.6, self_citation=0.2 | Author identity inference | Editor decision |

Same agent structure. Different governance parameters injected at instantiation.

### Five structural patterns observed across the implemented systems

These are descriptions of how the agents in the implemented systems are arranged — not
prescriptions. Other arrangements exist.

**Pattern 1: Sequential Convergence**
```
Scope → Gather → Synthesize → Conclude
```
Used in: AutoResearchClaw (research synthesis), decision-agent (procurement intake).
Each agent narrows the information space. Evidence accumulates toward a conclusion.

**Pattern 2: Adversarial Contest**
```
Proposer ↔ Challenger → Arbiter → Ruling
```
Used in: AutoDebate (option selection). Two agents contest a position. An arbiter rules.
The ruling includes a record of which arguments were accepted and rejected.

**Pattern 3: Parallel Intake → Convergent Gate**
```
[Scout A || Scout B || Scout C] → Evaluator → Recommender → Gate
```
Used in: decision-agent procurement runs (requirement_analyst, market_scout, risk_assessor
run in parallel, then evaluator and recommender run sequentially). Independent parallel
gathering converges at a single evaluation stage under a gate.

**Pattern 4: Threshold Monitor → Triggered Decision**
```
Monitor → Condition check → [if threshold crossed] → Authorize action → Audit
```
Seen in: DAR evidence floor check in the governed stack. If the PAAP score does not meet
the threshold, the action is blocked before the recommender runs. The LLM role here is
minimal — the threshold check is deterministic.

**Pattern 5: Iterative Refinement with Rollback**
```
Plan → Execute → Evaluate → [if insufficient] → Rollback to earlier stage → Re-execute
```
Used in: AutoResearchClaw PIVOT/REFINE loop. If the RESEARCH_DECISION stage returns PIVOT,
the pipeline rolls back to an earlier stage and re-executes. Rollback target is defined
per decision type, not chosen freely.

---

## 10. Novel Contributions Summary

1. **DSC (Decision Scope Contract)** — formal mechanism for making decision scope explicit
   and enforceable at runtime. Novel construct, not in prior literature.

2. **PAAP (Probabilistic Authority Assessment Protocol)** — quantitative evidence authority
   scoring framework with domain-injectable weights. Novel construct.

3. **DAR (Decision Authorization Record)** — deterministic authorization layer that issues
   traceable receipts (ALLOW / ESCALATE / DENY) based on consequence class and evidence
   floor. Novel construct.

4. **Combinatorial insufficiency argument** — formal argument that no combination of
   existing components (RAG, memory, fine-tuning, guardrails) produces normatively
   sufficient governance. Empirically supported by benchmark results.

5. **Dynamic agent composition** — the prototype selects agent topology, interaction
   pattern, and completion contract based on decision type. AutoResearchClaw uses sequential
   convergence; AutoDebate uses adversarial rounds. The governance layer sits on top of
   both, with domain parameters injected separately.

6. **Domain-injectable structural patterns** — the prototype separates agent structure from
   domain parameters. The same structural pattern (e.g. multi-source comparison) runs in
   procurement, CV screening, and other domains by injecting different governance parameters
   via DSC, PAAP, and DAR at instantiation.

---

## 11. Remaining Work Before Submission

1. **Cross-model benchmark** — run Ollama conditions (qwen2.5, llama3.1) to test
   governance stability across model swap. This is the most important remaining experiment.
   The claim that governance metrics are model-independent is currently unverified.

2. **Fix recommender contract** — add `evidence_sources_declared` to recommender validators
   so `recommendation_traceable` separates A0/A/C from F conditions.

3. **CV review domain benchmark** — shows a structurally different governance profile
   (DSC blocking protected-class inference). Strengthens the domain-independence claim.

4. **Increase reps** — run 3+ reps per condition to measure variance. The compliance-
   coverage frontier ordering at intermediate thresholds (0.30 vs 0.60) is not yet robust.

5. **Honest limitation statement** — synthetic fixtures, no live vendor data, single
   frontier model for most runs. These are valid scope boundaries for a master's thesis
   and should be stated explicitly.

---

## 12. Key Literature References (from thesis)

- Brown et al. [2020] — GPT-3, LLM public availability landmark
- Achiam et al. [2023] — GPT-4 technical report
- Lewis et al. [2020] — RAG original paper
- Wang et al. [2024] — multi-agent cooperation survey
- Sumers et al. [2024] — cognitive architectures for language agents
- Huang et al. [2023, 2024] — hallucination surveys
- Ji et al. [2023] — hallucination in NLG survey
- Xu et al. [2025] — formal proof that hallucination is architecturally inevitable in
  autoregressive generative paradigm
- Liu et al. [2024] — lost in the middle, long context performance degradation
- European Parliament [2024] — EU AI Act (2024/1689), high-risk system requirements
- NIST [2023] — AI Risk Management Framework
- Vaswani et al. [2017] — Transformer architecture
- Kaplan et al. [2020] — scaling laws
- LeCun [2022] — JEPA world models
- Sequeda et al. [2025] — structural gap between semantic reasoning and runtime control
- Veale & Zuiderveen Borgesius [2021] — EU AI Act compliance analysis
- McKinsey & Company [2024] — LLM deployment in enterprise
- Karpathy [2025] — harness architecture paradigm
- Anthropic [2024] — Claude system card, harness architecture
- Schluntz & Zhang [2024] — harness as separate architectural layer
- Packer et al. [2023] — memory and state management in agents
- Fedus et al. [2022] — mixture of experts (MoE)
- Arunkumar et al. [2026] — agent taxonomy
- Abou Ali et al. [2025] — multi-agent perception and tool use
