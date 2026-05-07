# Past Procurement Decisions

Record of completed procurement decisions for institutional learning.
Workers reference this registry to avoid repeating past mistakes and to apply proven patterns.

---

## Decision 2024-003: CRM Platform Selection

**Date completed:** 2024-09-15
**Budget:** EUR 85,000/year
**Winner:** HubSpot Sales Hub Professional
**Rejected:** Salesforce Sales Cloud, Pipedrive, Zoho CRM

**Key evaluation factors:**
- HubSpot scored highest on ease of adoption (no dedicated admin required)
- Salesforce eliminated due to EUR 140,000+ implementation cost (exceeded budget)
- Pipedrive lacked GDPR-compliant audit log for financial services requirement

**Evidence cited:**
- 3 reference customers in FinTech (verified via call)
- HubSpot GDPR compliance documentation (ISO 27001, SOC 2 Type II)
- Vendor proposals from all 4 vendors

**Risks materialised:**
- None in first year

**Lessons learned:**
- Implementation cost must be captured in initial RFP — "best licence price" is misleading
- Reference calls are more valuable than vendor case studies; insist on direct contact
- Negotiated 15% discount on annual subscription by committing to 2-year term

---

## Decision 2024-001: Document Management System

**Date completed:** 2024-03-20
**Budget:** EUR 30,000/year
**Winner:** SharePoint Online (M365 add-on)
**Rejected:** Confluence Cloud, Notion Business, Notion Enterprise

**Key evaluation factors:**
- SharePoint leveraged existing M365 Enterprise licence (near-zero additional cost)
- Confluence eliminated due to Atlassian data centre in US-East (data residency fail)
- Notion eliminated due to no DPA available at SMB tier at time of evaluation

**Evidence cited:**
- Existing M365 licence audit
- Atlassian trust portal (data region documentation)
- Notion DPA review (legal opinion)

**Risks materialised:**
- SharePoint adoption slower than expected; training required (2 days per team)

**Lessons learned:**
- Always check what is already licensed before evaluating new vendors
- Adoption cost (training, change management) is real; include in TCO
- Notion has since added EU data residency and DPA — may be reconsidered in 2026

---

## Decision 2023-005: Cloud Backup Solution

**Date completed:** 2023-11-10
**Budget:** EUR 12,000/year
**Winner:** Veeam Cloud Connect (via EU-hosted MSP)
**Rejected:** AWS Backup, Azure Backup

**Key evaluation factors:**
- Veeam + EU MSP partner gave lowest price by 40%
- AWS Backup requires data in AWS — migration cost too high given on-prem VMware estate
- Azure Backup similar issue

**Risks materialised:**
- RISK-011 (key person): MSP primary engineer left; 3-week degraded support period
  - Mitigated via escalation clause in contract
  - Resolution: MSP brought in replacement; no data loss

**Lessons learned:**
- SMB-tier MSP dependency is real; add MSP staff continuity clause to contract
- Test backup restores quarterly — vendor-confirmed backups are not the same as verified restores

---

## Decision 2023-002: HR Software

**Date completed:** 2023-05-30
**Budget:** EUR 20,000/year
**Winner:** Personio
**Rejected:** BambooHR, SAP SuccessFactors

**Key evaluation factors:**
- Personio: German-headquartered, EU data centre, strong DACH-specific payroll
- BambooHR: US-only data residency — immediate disqualifier for GDPR
- SAP SuccessFactors: EUR 80,000 implementation — budget exceeded

**Evidence cited:**
- Personio trust centre (SOC 2 Type II, ISO 27001)
- Legal review confirming Personio qualifies as EU processor under GDPR Art. 28
- 2 reference customers in Germany (mid-sized, similar industry)

**Risks materialised:**
- None

**Lessons learned:**
- GDPR data residency requirement eliminates many US-origin SaaS vendors at screening stage
- Build an elimination filter into evaluation framework to reduce wasted effort

---

## Patterns Across All Decisions

1. **Compliance acts as a hard eliminator** — non-compliant vendors should be screened out before detailed scoring
2. **Implementation cost is consistently underestimated** — always request all-in pricing
3. **Egress and data transfer costs surprise every project** — model them explicitly
4. **Reference calls are high-value evidence** — schedule them before shortlist decision
5. **Existing licences are underutilised** — audit before buying new
