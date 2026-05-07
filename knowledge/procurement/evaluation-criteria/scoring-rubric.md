# Evaluation Scoring Rubric

Standard rubric for scoring vendors across all procurement categories.
Evaluators must cite evidence sources for each score. Model inference alone is not acceptable.

---

## Scoring Scale

| Score | Label | Meaning |
|-------|-------|---------|
| 0 | Not Met | Requirement entirely absent; disqualifying if Must Have |
| 1 | Weak | Partial capability; significant gaps; workarounds required |
| 2 | Adequate | Meets minimum requirement; no notable strengths or gaps |
| 3 | Good | Clearly meets requirement; some notable strengths |
| 4 | Excellent | Exceeds requirement; industry-leading; reference-grade |

**Weighted score formula:**
`Weighted Score = Σ (Criterion Score × Criterion Weight)`

Maximum possible: 4.00

**Recommendation thresholds:**
- ≥ 3.20 = Strongly Recommend
- 2.60–3.19 = Recommend with conditions
- 2.00–2.59 = Marginal — escalate for human review
- < 2.00 = Do Not Recommend

---

## Criterion 1: Technical Fit (Default weight: 35%)

Assess whether the vendor's solution meets the functional and non-functional requirements.

| Score | Evidence Required | Example |
|-------|------------------|---------|
| 0 | Feature absent from documentation | No managed Kubernetes offering |
| 1 | Feature present but requires significant configuration | K8s but no managed control plane |
| 2 | Meets spec with standard configuration | Managed K8s, basic SLA |
| 3 | Meets spec with enhanced capability | Managed K8s + auto-scaling, 99.95% SLA |
| 4 | Industry-leading; sets the benchmark | GKE Autopilot; reference K8s implementation |

**Evidence sources accepted:** product documentation, PoC results, third-party benchmarks, architecture reviews

---

## Criterion 2: Commercial Terms (Default weight: 25%)

Assess total cost of ownership, pricing model, and contractual flexibility.

| Score | Evidence Required | Example |
|-------|------------------|---------|
| 0 | Price exceeds budget ceiling | Quote > EUR 50,000/year ceiling |
| 1 | Price 20–40% over budget; requires scope cut | EUR 60,000 on-demand; EUR 48,000 with reservations |
| 2 | Within budget; standard market pricing | EUR 42,000/year all-in |
| 3 | Within budget; below market average | EUR 32,000/year with volume discount |
| 4 | Significantly below market; favourable flexibility | EUR 20,000/year; monthly billing; no exit penalty |

**Evidence sources accepted:** signed vendor proposal, market pricing benchmarks, reference quotes

---

## Criterion 3: Compliance & Security (Default weight: 20%)

Assess certifications, data residency, and security posture.

| Score | Evidence Required | Example |
|-------|------------------|---------|
| 0 | Fails hard requirement (GDPR, ISO 27001 if required) | No EU data residency; no DPA available |
| 1 | Partial compliance; compensating controls needed | ISO 27001 but DPA non-standard |
| 2 | Meets all hard requirements | ISO 27001 current, GDPR DPA, EU data residency |
| 3 | Exceeds requirements; additional assurance | ISO 27001 + SOC 2 + annual pen test reports |
| 4 | Sector-leading security posture + transparency | Above + Bug bounty + transparency report |

**Evidence sources accepted:** ISO certificate (from accreditation body), SOC 2 audit report, vendor trust portal, legal DPA review

**Note:** Any vendor scoring 0 on compliance is automatically disqualified regardless of other scores.

---

## Criterion 4: Vendor Capability & References (Default weight: 15%)

Assess vendor maturity, financial stability, and customer references.

| Score | Evidence Required | Example |
|-------|------------------|---------|
| 0 | Unable to provide references or financials | Start-up, 1 year old, no audited accounts |
| 1 | Limited references; uncertain financials | 2 references, unaudited accounts |
| 2 | Adequate references; stable finances | 3 verified references, 3 years audited accounts |
| 3 | Strong references in same sector | 5+ references, same industry, strong financials |
| 4 | Market-leader; globally recognised | Thousands of customers; public company or well-capitalised |

**Evidence sources accepted:** reference customer calls (not written testimonials alone), company accounts (Companies House / equivalent), analyst reports (Gartner, Forrester)

---

## Criterion 5: Implementation Approach (Default weight: 5%)

Assess implementation plan, timeline, and migration support.

| Score | Evidence Required | Example |
|-------|------------------|---------|
| 0 | No implementation plan provided | |
| 1 | Generic plan; no milestones | |
| 2 | Milestone-based plan; reasonable timeline | |
| 3 | Detailed plan; dedicated implementation manager | |
| 4 | Fixed-price implementation; risk shared with vendor | |

---

## Disqualification Criteria

The following are automatic disqualifiers regardless of score:

1. **No GDPR DPA available** when processing personal data of EU residents
2. **ISO 27001 not current** when specified as mandatory in requirements
3. **Price exceeds budget ceiling** (unless explicitly noted as negotiable)
4. **Data residency outside required region**
5. **Unable to meet minimum security requirements** (e.g., no MFA, no encryption at rest)

---

## Evidence Hierarchy

Evidence must be cited with authority weight. Higher weight = more credible.

| Evidence Type | Authority Weight | Notes |
|---------------|-----------------|-------|
| Signed contract / formal proposal | 1.00 | Legal commitment |
| Certified audit report (ISO, SOC 2) | 0.95 | Independent third-party |
| Reference customer (direct call) | 0.85 | Verified first-hand |
| Vendor trust portal documentation | 0.70 | Vendor-published |
| Analyst report (Gartner, Forrester) | 0.65 | Independent but not vendor-specific |
| Written case study / testimonial | 0.50 | Vendor-curated |
| Market benchmark data | 0.45 | General; not vendor-specific |
| Web research / press coverage | 0.30 | Uncurated |
| Model inference / reasoning alone | 0.00 | NOT acceptable as evidence |
