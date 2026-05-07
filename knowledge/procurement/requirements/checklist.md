# Procurement Requirements Checklist

Use this checklist before moving from requirements to vendor selection.

## Completeness

- [ ] Business problem clearly stated — not a solution looking for a problem
- [ ] All functional requirements documented with MoSCoW priorities
- [ ] Non-functional requirements include measurable metrics (not just "fast" or "secure")
- [ ] Budget ceiling confirmed and signed off by budget owner
- [ ] Timeline reviewed for feasibility (minimum 6 weeks for competitive tender)
- [ ] Stakeholder sign-off obtained from: technical lead, legal, finance, operations

## Technical Requirements

- [ ] Integration requirements listed (APIs, SSO, data formats)
- [ ] Data volumes specified (storage, throughput, concurrent users)
- [ ] Supported environments specified (cloud provider, OS, browser)
- [ ] Disaster recovery / RTO and RPO defined
- [ ] Security requirements aligned with internal classification policy

## Compliance Checklist

- [ ] GDPR applicability assessed — if processing personal data of EU residents: DPA required
- [ ] Data residency constraint documented (EU-only, or specific country)
- [ ] ISO 27001 or equivalent certification required? Y / N
- [ ] SOC 2 Type II report required? Y / N
- [ ] Public procurement thresholds checked:
  - Goods/services < EUR 140,000: simplified procedure acceptable
  - Goods/services ≥ EUR 140,000: full tender process required
- [ ] Export control assessment (EAR/ITAR) if technology is US-origin
- [ ] Sector-specific regulation checked (financial: MiFID II, health: MDR, etc.)

## Vendor Requirements

- [ ] Minimum vendor financial stability criteria defined (e.g., 3 years audited accounts)
- [ ] Reference customer requirements set (number, sector, size)
- [ ] Sub-contractor disclosure required? Y / N
- [ ] Insurance requirements specified (PI, PL, cyber)
- [ ] Data breach notification SLA requirement stated (e.g., 72 hours per GDPR Art. 33)

## Contractual Requirements

- [ ] IP ownership clause agreed (especially for bespoke development)
- [ ] Source code escrow required? Y / N
- [ ] Exit assistance clause required (data export, knowledge transfer)
- [ ] Penalty / service credits for SLA breach defined
- [ ] Termination for convenience clause required? Y / N
- [ ] Governing law and jurisdiction specified

## Common Pitfalls to Avoid

1. **Specifying a solution instead of a need** — "We need Salesforce" vs "We need CRM capability for 50 users"
2. **Underestimating integration complexity** — SSO, existing data pipelines
3. **Ignoring total cost of ownership** — licence + implementation + training + ongoing support
4. **No data migration plan** — exit from incumbent may be expensive
5. **Budget ceiling set too low** — market research before budget finalisation
6. **No incumbent analysis** — understand switching costs and current contract exit terms
