# CV Evaluation Use Case

Date: 2026-05-13
Purpose: describe CV evaluation as a governed decision architecture example.

---

## Case

A company receives candidate CVs for an open role and wants the system to evaluate fit
against a job specification. The system should extract role-relevant experience, compare
the candidate against required skills, identify gaps, produce a structured evaluation, and
recommend whether the candidate should proceed to the next hiring stage.

Input example:

```text
job specification
-> required skills
-> nice-to-have skills
-> seniority level
-> location / work authorization constraints
-> interview rubric

candidate CV
-> work history
-> education
-> certifications
-> projects
-> skills
```

The final output should be a decision-support artifact, not an autonomous hiring decision.

## Why the Governed Architecture Is Useful

CV evaluation is high-risk because the model can easily use irrelevant or legally sensitive
signals. A plain model may infer age, gender, nationality, family status, ethnicity, health,
or other protected characteristics from names, dates, photos, schools, addresses, gaps, or
language patterns.

The governed architecture is useful because it can separate:

```text
role-relevant evidence
```

from:

```text
protected or irrelevant personal signals
```

The task changes from:

```text
prompt -> candidate recommendation
```

to:

```text
CV + job spec
-> decision router
-> CV evaluation architecture
-> bounded worker contracts
-> CV parsing
-> requirement matching
-> evidence-grounded scoring
-> bias / protected-class check
-> recommendation memo
-> authorization policy
-> audit record
```

## Suggested Worker Topology

```text
cv_parser
job_spec_parser
        ↓
requirement_matcher
        ↓
experience_evaluator
        ↓
gap_and_risk_checker
        ↓
bias_scope_checker
        ↓
recommendation_writer
        ↓
decision_gate
```

A more parallel version:

```text
cv_parser ───────────────┐
job_spec_parser ─────────┼──> requirement_matcher -> evaluator -> recommendation_writer
credential_checker ──────┘
bias_scope_checker ───────────────────────────────> decision_gate
```

## Core Structured Output

The central artifact should be a structured evaluation table, not only prose feedback.

Each evaluation item should contain:

- requirement ID
- requirement description
- candidate evidence
- evidence source location
- match level
- confidence
- gap description
- interviewer follow-up question
- excluded signals
- scoring rationale

The hiring memo should be generated from this structured evaluation.

## Evidence Profile

CV evaluation needs an evidence taxonomy focused on role relevance and legal safety.

Suggested evidence authority:

| Evidence type | Authority |
|---|---:|
| job_requirement | high |
| candidate_cv_claim | medium |
| verified_credential | high |
| portfolio_or_work_sample | high |
| recruiter_note | medium |
| interview_result | high, if structured |
| model_inference | zero or very low |
| protected_characteristic | forbidden |

Every score should trace to:

```text
job requirement
+ candidate-provided or verified evidence
+ explicit scoring rubric
```

The model should not score based on unstated preferences, inferred personality traits, or
protected characteristics.

## Validation Requirements

CV evaluation requires validators that check both structure and prohibited reasoning.

Required validators:

- job relevance validator: every score must map to a job requirement
- evidence validator: every candidate claim must cite the CV, credential, portfolio, or interview record
- protected-class validator: output must not use protected characteristics or proxies
- inference validator: model inference cannot be cited as hiring evidence
- scoring rubric validator: scores must use the configured rubric, not free-form judgment
- explanation validator: rejection or advancement rationale must be specific and job-related
- audit validator: all inputs, scores, exclusions, and recommendation events must be recorded

## Governance Profile

DSC scope control:

- Only role-relevant evidence is allowed.
- Protected characteristics and proxies are out of scope.
- The system must not infer age, gender, ethnicity, nationality, family status, disability,
  health, religion, or similar protected traits.
- Personal style, name origin, photo appearance, address, graduation year, or employment gaps
  must not be used unless explicitly relevant under policy and law.

PAAP evidence scoring:

- Verified credentials and work samples receive high authority.
- Candidate CV claims receive medium authority unless independently verified.
- Recruiter notes receive medium authority.
- Model inference receives zero authority.
- Protected characteristics are not merely low authority; they are forbidden evidence.

DAR authorization:

- Internal structured evaluation can be allowed if scope and evidence checks pass.
- Recommendation to interview can be allowed or escalated depending on company policy.
- Automatic rejection should be denied or escalated unless strict legal and policy controls exist.
- Final hiring decisions should require human review.

## Human Interaction Policy

Unlike construction quote dispatch, CV evaluation should normally keep a human in the loop
for consequential decisions. The system can prepare a ranking, memo, or interview
recommendation, but it should not autonomously reject or hire a candidate.

Practical policy:

```text
ALLOW:
  parse CV
  extract structured experience
  compare against job requirements
  generate interview questions
  produce recommendation memo

ESCALATE:
  shortlist candidate
  reject candidate
  advance candidate to final stage

DENY:
  use protected or inferred personal traits
  make final hire/no-hire decision autonomously
```

## Fit With the Existing Architecture

This can reuse the current architecture pattern:

```text
decision router
architecture proposal
worker contracts
scheduler
tool-bounded workers
output validators
DSC
PAAP
DAR
audit log
run artifacts
```

What needs to be added is a new domain:

```text
cv_evaluation
```

This domain should define:

- worker catalog
- topology
- output schemas
- job requirement taxonomy
- evidence authority weights
- protected-signal blocklist
- scoring rubric validators
- advancement/rejection authorization rules

## Main Design Conclusion

The CV case is a strong fit for the governed architecture because the main risk is not
calculation error but scope error: the model may use information that should not be part
of the decision.

The architecture is suitable if the final design keeps this boundary:

```text
LLM: extract CV facts, map evidence to job requirements, draft rationale.
Code: enforce protected-signal rules, validate evidence, apply scoring rubric, authorize next action.
Human: owns consequential hiring decisions.
```

The procurement case proves evidence and authorization control. The construction pricing
case proves deterministic validation before external action. The CV evaluation case proves
scope control: the system must know not only what evidence is strong, but what evidence is
forbidden.
