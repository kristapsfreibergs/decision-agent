# Procurement Risk Patterns

Recurring risk patterns observed across procurement decisions.
Use this registry to ensure risk assessment workers cite known patterns.

---

## Category 1: Vendor Lock-In

### RISK-001: Proprietary API / Data Format Lock-In
- **Pattern:** Vendor uses non-standard APIs or data formats with no export path
- **Likelihood:** High (common with SaaS, low with IaaS)
- **Impact:** High — migration cost can exceed 2× original contract value
- **Mitigation:**
  - Require open API standards (REST/OpenAPI, S3-compatible storage)
  - Contractual data export obligation within 30 days of termination
  - Evaluate portability during technical assessment
- **Past occurrences:** CRM replacement 2022, ERP evaluation 2023

### RISK-002: Kubernetes / Container Platform Lock-In
- **Pattern:** Proprietary Kubernetes distributions or CNI plugins prevent migration
- **Likelihood:** Medium
- **Impact:** Medium — 3–6 months migration effort
- **Mitigation:**
  - Use CNCF-conformant Kubernetes distributions only
  - Avoid proprietary node pool features in manifests
  - Require workload portability demo during PoC

### RISK-003: Managed Service Dependency Cascade
- **Pattern:** Choosing managed DB, cache, and queue from same vendor creates bundle lock-in
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:** Evaluate open-source self-hosted alternatives for non-critical tiers

---

## Category 2: Compliance Failure

### RISK-004: Data Residency Violation
- **Pattern:** Vendor claims EU hosting but uses US-based support or CDN nodes that process data
- **Likelihood:** Medium (especially with US-headquartered vendors)
- **Impact:** Very High — GDPR fines up to 4% global turnover; reputational damage
- **Mitigation:**
  - Request Data Transfer Impact Assessment (DTIA)
  - Verify Schrems II compliance stance
  - Require contractual binding for EU-only processing

### RISK-005: Certification Lapse
- **Pattern:** Vendor holds ISO 27001 at time of award but lets it lapse during contract
- **Likelihood:** Low (but has occurred)
- **Impact:** High — may trigger compliance breach if certification was contractual condition
- **Mitigation:**
  - Include clause requiring notification of certification change within 5 business days
  - Annual certificate verification by procurement team

### RISK-006: GDPR Processor Agreement Not Executed
- **Pattern:** Technical team proceeds with vendor without formal DPA in place
- **Likelihood:** Medium (common with SMB-tier vendors)
- **Impact:** High — technical GDPR violation from day one of processing
- **Mitigation:**
  - DPA is a hard blocker; no contract award without signed DPA
  - Legal review of DPA for standard clauses

---

## Category 3: Commercial Risk

### RISK-007: Budget Overrun — Egress Costs
- **Pattern:** Cloud provider egress fees not modelled during evaluation; actual costs 2–3× estimate
- **Likelihood:** High (consistently under-estimated)
- **Impact:** Medium (budget overrun 20–40%)
- **Mitigation:**
  - Measure actual data transfer from incumbent or prototype
  - Include egress in TCO model explicitly
  - Consider egress-free providers (Hetzner, Cloudflare R2) for storage-heavy workloads

### RISK-008: Reserved Instance Commitment Without Baseline
- **Pattern:** Team commits to 1–3 year reserved capacity before usage baseline is established
- **Likelihood:** Medium
- **Impact:** Medium — stranded capacity cost
- **Mitigation:**
  - Pilot 3 months on-demand before committing to reservations
  - Use savings plans (AWS/Azure/GCP) for flexibility

### RISK-009: Hidden Implementation Cost
- **Pattern:** Low licence fee but high implementation/onboarding cost not captured in evaluation
- **Likelihood:** High
- **Impact:** Medium
- **Mitigation:**
  - Request all-in pricing including: onboarding, training, migration support, first-year professional services

---

## Category 4: Operational Risk

### RISK-010: Single Point of Failure — Vendor Support
- **Pattern:** Vendor has no 24/7 support; critical incidents handled in business hours only
- **Likelihood:** Medium
- **Impact:** High for production workloads
- **Mitigation:**
  - Require 24/7 support SLA with ≤ 1 hour P1 response time
  - Verify support structure before award

### RISK-011: Key Person Dependency at Vendor
- **Pattern:** SMB vendor where all domain knowledge is held by 1–2 individuals
- **Likelihood:** High for SMB vendors
- **Impact:** High — service degradation or collapse if key person leaves
- **Mitigation:**
  - Request org chart and succession plan
  - Prefer vendors with > 50 employees for critical systems

### RISK-012: Vendor Financial Instability
- **Pattern:** Vendor acqui-hired, acquired, or goes insolvent during contract
- **Likelihood:** Low (but high impact)
- **Impact:** Very High
- **Mitigation:**
  - Require 3 years audited financial statements
  - Source code escrow for bespoke software
  - Termination-for-convenience clause allowing immediate exit
