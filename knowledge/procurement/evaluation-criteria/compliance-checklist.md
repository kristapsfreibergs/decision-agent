# Compliance Evaluation Checklist

This checklist is completed during vendor evaluation.
Any FAIL on a mandatory item is an automatic disqualifier.

---

## Section 1: GDPR Compliance

| # | Check | Mandatory | Pass / Fail | Evidence Required |
|---|-------|-----------|-------------|-------------------|
| 1.1 | Vendor can process data with EU data residency | Yes | | Trust portal, DPA |
| 1.2 | Data Processing Agreement (DPA) available | Yes | | Signed DPA or DPA template |
| 1.3 | DPA includes Standard Contractual Clauses (SCCs) or equivalent | Yes | | DPA document |
| 1.4 | Data breach notification within 72 hours (GDPR Art. 33) | Yes | | DPA / SLA terms |
| 1.5 | Right to erasure (GDPR Art. 17) supported | Yes | | DPA / product documentation |
| 1.6 | Data portability (GDPR Art. 20) supported | Yes | | Product documentation |
| 1.7 | Sub-processors listed and DPA covered | Yes | | DPA sub-processor list |
| 1.8 | Schrems II compliance posture documented | Recommended | | DTIA or DPA addendum |

---

## Section 2: Security Certifications

| # | Check | Mandatory | Pass / Fail | Evidence Required |
|---|-------|-----------|-------------|-------------------|
| 2.1 | ISO/IEC 27001:2022 (or 2017) certificate current | Yes* | | Certificate from accreditation body |
| 2.2 | Certificate covers scope relevant to this service | Yes* | | Certificate scope statement |
| 2.3 | SOC 2 Type II report available | Recommended | | Audit report (NDA may be required) |
| 2.4 | Penetration testing conducted in last 12 months | Recommended | | Test summary or attestation |
| 2.5 | Vulnerability disclosure policy / bug bounty program | No | | Public policy URL |

*Mandatory only when ISO 27001 is specified as a requirement in the procurement specification.

---

## Section 3: Data Residency

| # | Check | Mandatory | Pass / Fail | Evidence Required |
|---|-------|-----------|-------------|-------------------|
| 3.1 | Primary data stored in required region | Yes | | Architecture diagram, DPA |
| 3.2 | Backups stored in required region | Yes | | DPA, technical documentation |
| 3.3 | Monitoring / logging data in required region | Recommended | | Technical documentation |
| 3.4 | Support access limited to required region | Recommended | | DPA, support model documentation |
| 3.5 | CDN / edge nodes do not cache personal data outside region | Yes (if CDN used) | | DPA, CDN configuration |

---

## Section 4: Access Control & Identity

| # | Check | Mandatory | Pass / Fail | Evidence Required |
|---|-------|-----------|-------------|-------------------|
| 4.1 | Multi-factor authentication (MFA) supported | Yes | | Product documentation |
| 4.2 | SAML 2.0 or OIDC SSO integration available | Recommended | | Product documentation |
| 4.3 | Role-based access control (RBAC) | Yes | | Product documentation |
| 4.4 | Audit log of administrative actions | Yes | | Product documentation |
| 4.5 | Encryption at rest (AES-256 or equivalent) | Yes | | Security whitepaper |
| 4.6 | Encryption in transit (TLS 1.2 minimum, TLS 1.3 preferred) | Yes | | Security whitepaper |

---

## Section 5: Business Continuity

| # | Check | Mandatory | Pass / Fail | Evidence Required |
|---|-------|-----------|-------------|-------------------|
| 5.1 | Recovery Time Objective (RTO) meets requirement | Yes | | SLA documentation |
| 5.2 | Recovery Point Objective (RPO) meets requirement | Yes | | SLA documentation |
| 5.3 | Business Continuity Plan (BCP) documented | Recommended | | BCP summary |
| 5.4 | Disaster Recovery tested in last 12 months | Recommended | | DR test report or attestation |
| 5.5 | Geographic redundancy (multi-AZ or multi-region) | Yes (for HA requirements) | | Architecture documentation |

---

## Section 6: Contractual Compliance

| # | Check | Mandatory | Pass / Fail | Evidence Required |
|---|-------|-----------|-------------|-------------------|
| 6.1 | Vendor accepts our standard DPA | Yes | | Signed DPA |
| 6.2 | Liability cap adequate for risk exposure | Yes | | Contract terms |
| 6.3 | Termination for convenience clause | Yes | | Contract terms |
| 6.4 | Exit assistance and data return obligation | Yes | | Contract terms |
| 6.5 | Change of control notification obligation | Recommended | | Contract terms |
| 6.6 | No unilateral price change within contract term | Yes | | Contract terms |

---

## Compliance Score Summary

| Section | Items | Mandatory Fails | Recommendation |
|---------|-------|-----------------|----------------|
| 1. GDPR | 8 | | |
| 2. Security Certifications | 5 | | |
| 3. Data Residency | 5 | | |
| 4. Access Control | 6 | | |
| 5. Business Continuity | 5 | | |
| 6. Contractual | 6 | | |
| **Total** | **35** | **0 to proceed** | |

**Rule:** Any mandatory FAIL → vendor is disqualified. Do not proceed to commercial or technical scoring.
