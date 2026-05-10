# Pricing Benchmarks

Reference pricing for cloud infrastructure services. Benchmarks are indicative; actual quotes
may differ by 10–40% based on commitment, volume, and negotiation.

**Last updated:** 2026-01-10
**Currency:** EUR (approximate; converted from USD at 1.08)
**Use as `created_at`:** 2026-01-10 when citing this file as a `market_benchmark` evidence source.

---

## Managed Kubernetes (per cluster/month)

| Provider | Small (≤10 nodes) | Medium (10–50 nodes) | Notes |
|----------|-------------------|----------------------|-------|
| AWS EKS | EUR 72 | EUR 72 + node cost | Control plane flat fee |
| Azure AKS | EUR 0 (free tier) | EUR 0 + node cost | Control plane free |
| GCP GKE | EUR 0 (1 cluster free) | EUR 92 + node cost | Autopilot option available |
| Hetzner | N/A (self-managed only) | — | No managed offering |
| OVHcloud MKS | EUR 30 | EUR 30 + node cost | |

**Node compute cost (general purpose, 4 vCPU / 16 GB RAM, on-demand):**

| Provider | Per node/month |
|----------|---------------|
| AWS (m6i.xlarge) | EUR 170 |
| Azure (D4s v5) | EUR 180 |
| GCP (n2-standard-4) | EUR 155 |
| Hetzner (CX42) | EUR 30 |
| OVHcloud (b3-8) | EUR 85 |

---

## Managed PostgreSQL (per instance/month)

### Small (2 vCPU, 8 GB RAM, 100 GB SSD)

| Provider | On-demand | Reserved 1yr | Reserved 3yr |
|----------|-----------|--------------|--------------|
| AWS RDS PostgreSQL | EUR 180 | EUR 115 | EUR 75 |
| Azure DB for PostgreSQL | EUR 160 | EUR 105 | EUR 70 |
| GCP Cloud SQL | EUR 170 | EUR 105 | EUR 70 |
| Hetzner (self-managed) | EUR 20 compute | — | — (no managed) |
| OVHcloud | EUR 90 | — | — |

### Multi-AZ / High Availability premium: +80–120% on base price

---

## Object Storage (per TB/month stored + egress)

| Provider | Storage/TB | Egress to internet/TB | Egress within region |
|----------|------------|----------------------|----------------------|
| AWS S3 | EUR 22 | EUR 85 | EUR 9 |
| Azure Blob | EUR 19 | EUR 80 | EUR 9 |
| GCP Cloud Storage | EUR 20 | EUR 110 | EUR 0 |
| Hetzner Object Storage | EUR 5 | EUR 0 (1 TB free/month) | EUR 0 |
| OVHcloud | EUR 11 | EUR 11 | EUR 0 |

---

## Total Cost of Ownership — Illustrative Scenario

**Scenario:** Decision-agent backend
- 3-node Kubernetes cluster (4 vCPU / 16 GB RAM per node)
- 1× PostgreSQL instance, HA, 200 GB
- 1 TB object storage, 500 GB egress/month

| Provider | Monthly (on-demand) | Annual (1yr commit) | Notes |
|----------|---------------------|---------------------|-------|
| AWS | EUR 950 | EUR 7,200 | Moderate with reserved |
| Azure | EUR 900 | EUR 6,800 | Free AKS control plane saves |
| GCP | EUR 850 | EUR 6,400 | Sustained-use discounts auto |
| Hetzner | EUR 180 | EUR 2,160 | Self-managed K8s + DB overhead |
| OVHcloud | EUR 480 | EUR 5,760 | |

**Note:** Hetzner estimate excludes engineering cost for self-managed K8s and PostgreSQL
(estimate 2–4 engineering days/month operational overhead = EUR 3,000–6,000/year at market rate).
Adjusted Hetzner TCO: EUR 5,160–8,160/year.

---

## Support Cost Benchmarks

| Provider | Entry Tier | Enterprise Tier | Notes |
|----------|-----------|-----------------|-------|
| AWS | EUR 0 (basic) | EUR 15,000+/yr | Developer: EUR 28/mo |
| Azure | EUR 0 (basic) | EUR 25,000+/yr | |
| GCP | EUR 0 (basic) | EUR 12,000+/yr | |
| Hetzner | EUR 0 | No enterprise tier | Ticket-based only |
| OVHcloud | EUR 0 | EUR 1,200+/yr | |

---

## Budget Planning Rules of Thumb

1. For hosted workloads requiring HA and compliance, budget EUR 10,000–30,000/year for cloud infrastructure
2. Hyperscaler (AWS/Azure/GCP) reserved 1-year pricing saves ~35%; 3-year saves ~55% vs on-demand
3. Egress costs are frequently underestimated; measure actual data transfer before committing
4. Add 15–20% buffer for data transfer, monitoring, logging, and ancillary services
5. Support contracts: add EUR 15,000–25,000/year for enterprise-grade SLA if required
