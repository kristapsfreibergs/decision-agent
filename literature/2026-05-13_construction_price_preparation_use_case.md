# Construction Price Preparation Use Case

Date: 2026-05-13
Purpose: describe construction price preparation as a governed production workflow.

---

## Case

A construction company receives a drawing and must prepare a price offer. The drawing has
already been converted into structured drawing facts by an external extraction step. The
system must read those facts, identify priced work items, assign quantities and costs, build
a quote, and send it without human interaction when all safety checks pass.

Input example:

```text
drawing facts
-> rooms, walls, openings, surfaces, measurements, annotations
-> requested work scope
-> client/project metadata
-> pricing catalog or supplier price list
```

The PDF/image ingestion layer can be added later. For the architecture discussion, the
decision system starts after drawing extraction:

```text
PDF / CAD / image
-> extraction layer
-> structured drawing facts
-> governed estimating architecture
```

## Why the Same Architecture Still Applies

This is not primarily a vendor-selection decision. It is a governed production workflow:

```text
drawing facts
-> quantity takeoff
-> work package mapping
-> price lookup
-> deterministic calculation
-> quote generation
-> automatic dispatch if authorized
```

The existing architecture is still useful because the task has bounded stages, evidence
requirements, deterministic validation needs, and an externally consequential final action.

The important distinction is:

```text
LLM extracts, classifies, and explains.
Deterministic code calculates, validates, authorizes, and sends.
```

The model should not be trusted to perform final arithmetic or decide whether an
externally binding quote is safe to send. Those checks should be deterministic.

## Suggested Worker Topology

```text
drawing_reader
    ↓
scope_extractor
    ↓
quantity_takeoff
    ↓
work_package_mapper
    ↓
price_resolver
    ↓
estimate_calculator
    ↓
quote_builder
    ↓
send_authorizer
    ↓
dispatcher
```

A more parallel version:

```text
drawing_reader
    ↓
scope_extractor
    ↓
quantity_takeoff ───────┐
work_package_mapper ────┼──> estimate_calculator -> quote_builder -> dispatcher
price_resolver ─────────┘
risk_checker ───────────┘
```

## Core Structured Output

The central artifact should be a bill of quantities / estimate table, not only a prose
quote.

Each line item should contain:

- line item ID
- drawing reference
- work category
- description
- quantity
- unit
- unit price
- price source
- labor component
- material component
- waste factor
- subtotal
- confidence
- assumptions
- exclusions

The quote document or email should be generated from this structured artifact.

## Evidence Profile

Construction pricing needs a different evidence taxonomy from procurement.

Suggested evidence authority:

| Evidence type | Authority |
|---|---:|
| drawing_measurement | high |
| client_scope_note | high |
| approved_price_catalog | high |
| supplier_price_list | medium/high |
| historical_job_cost | medium |
| estimator_assumption | low |
| model_inference | zero or very low |

Every estimate line should trace to:

```text
drawing element or scope note
+ price source
+ deterministic formula
```

## Validation Requirements

This domain needs stronger deterministic validators than procurement because arithmetic
and quantity errors directly affect price.

Required validators:

- drawing coverage validator: every priced item references a drawing element or scope note
- scope validator: no work outside the drawing/scope is priced unless listed as an assumption
- quantity validator: quantities have unit, source, and confidence
- price validator: every unit price comes from an approved catalog, supplier list, or allowed assumption
- arithmetic validator: quantity, unit price, waste, margin, tax, and total are recomputed by code
- quote completeness validator: required commercial terms are present
- send authorization validator: automatic sending is allowed only when all thresholds pass

## Automatic Sending Policy

Sending a price offer is an external commercial action. It can create financial and legal
risk. Therefore the dispatcher should not send merely because the model produced a quote.

Automatic send can be allowed only when all conditions pass:

- all required drawing areas were parsed
- every line item has a drawing/scope reference
- every quantity has a unit and confidence above threshold
- every unit price comes from an approved source
- all arithmetic checks pass
- total value is below the configured automatic-send threshold
- no unresolved assumptions require client clarification
- no exclusion changes the commercial meaning of the quote
- quote template and recipient are valid

If these checks fail:

```text
do not send
record blocked status
produce audit reason
optionally create a draft for later review
```

This preserves the requirement of no human interaction during the run while preventing
unsafe automatic dispatch.

## Governance Profile

DSC scope control:

- The system may only price work grounded in drawing facts, client scope, or explicit assumptions.
- It must not add unrelated work packages.
- It must not infer hidden site conditions unless marked as an assumption.

PAAP evidence scoring:

- Drawing measurements and approved price catalogs receive high score.
- Supplier price lists receive medium/high score depending on freshness.
- Historical costs are useful but should not override current approved pricing.
- Model inference should not be accepted as a price or quantity source.

DAR authorization:

- Internal estimate calculation can be allowed.
- Quote document creation can be allowed if validation passes.
- Sending the quote externally should be allowed only under strict thresholds.
- High-value, low-confidence, or assumption-heavy quotes should be denied or held as drafts.

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
construction_price_preparation
```

This domain should define:

- worker catalog
- topology
- output schemas
- evidence taxonomy
- price-source authority weights
- quantity and arithmetic validators
- automatic-send authorization rules

It does not require replacing the existing system. It requires extending the domain catalog
and adding construction-specific validators.

## Main Design Conclusion

The procurement case proves the architecture is useful for governed decisions. The
construction pricing case extends the same idea to governed production: the system does
not merely answer a question, it produces and may dispatch a commercial artifact.

The architecture is suitable if the final design keeps this boundary:

```text
LLM: read, extract, classify, explain, draft.
Code: calculate, validate, authorize, send.
```

That boundary is more important in construction pricing than in procurement because price
errors can be immediate, contractual, and expensive.
