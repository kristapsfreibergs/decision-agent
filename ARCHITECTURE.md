# Architecture

Decision Agent starts as a Python backend/runtime with a lightweight browser cockpit for
building the larger dynamic decision harness.

The immediate goal is narrow:

```text
coordinate bounded build agents using executable contracts
```

For a Mermaid view of the current component map and run lifecycle, see
[docs/current-architecture.md](docs/current-architecture.md).

This is intentionally smaller than the final personal/company assistant. It proves the core control principle first: agents do not operate under soft Markdown instructions alone. They operate inside an executable decision architecture.

## Core Thesis

Autonomous systems should not route tasks directly to a generic agent. They should classify the decision type, select or synthesize a decision-specific architecture, instantiate bounded workers, validate outputs, gate actions, and record outcomes.

For the bootstrap phase:

```text
software build request
-> software_project_build_task
-> software-scaffold-build/v1
-> scoped worker contracts
-> integration gate
-> audit/outcome record
```

## Hard Rules

- Markdown guidance is advisory; contracts are authoritative.
- Every run has a `run_id`.
- Every decision task has a `decision_id`.
- Every selected architecture is recorded.
- Every worker has explicit read paths, write paths, allowed tools, max steps, validators, and output schema.
- Workers do not execute final actions directly.
- File writes by workers must be constrained by declared write scope.
- High-risk or externally consequential actions require a decision gate.
- Provider-specific model code must live behind a provider seam.
- Outcome records are append-only.
- Runtime data is written under `data/`.

## Layer Architecture

### High-level view — complete industry stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  IDENTITY + AUTHORIZATION                                                   │
│  SSO/OIDC · RBAC · tenant isolation · named audit actors                   │
│  role-based gate approval · multi-person (4-eyes) authorization            │
│  ✗ not built                                                                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ authenticated + authorized request
┌────────────────────────────────▼────────────────────────────────────────────┐
│  EXPERIENCE LAYER                                                           │
│  Browser cockpit (governance.html / index.html)  ·  CLI  ·  REST API       │
│  ✓ built                                                                    │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ task + identity context
┌────────────────────────────────▼────────────────────────────────────────────┐
│  REQUEST GATEWAY + PII BOUNDARY                                             │
│  decision router · domain classifier · clarification flow                  │
│  data classification · PII detection · purpose gate (GDPR Art. 5)         │
│  pseudonymisation before LLM sees personal data                            │
│  ✓ routing built · ✗ PII / classification not built                        │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ classified, scoped, anonymised task
┌────────────────────────────────▼────────────────────────────────────────────┐
│  ORCHESTRATION + JOB QUEUE                                                  │
│  architecture registry · proposal builder · contract generator             │
│  dependency-aware scheduler · phase gate manager                           │
│  persistent job queue (pause / resume / external webhook triggers)         │
│  scheduled polling · long-running state across days or weeks               │
│  ✓ orchestration built · ✗ persistent queue not built                      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ worker contracts (bounded)
┌────────────────────────────────▼────────────────────────────────────────────┐
│  WORKER EXECUTION + OUTPUT QUALITY                                          │
│  worker runner · tool provider · output validator                          │
│  checkpoint + retry · exponential backoff · fallback provider              │
│  [ requirement_analyst | market_scout | risk_assessor | evaluator | recommender ] │
│  critic agent: grounding check · factual consistency · hallucination detect│
│  ✓ execution + retry built · ✗ critic agent not built                      │
└──────────┬──────────────────────────────────────────────┬───────────────────┘
           │ evidence requests                            │ tool calls
┌──────────▼────────────────┐              ┌─────────────▼────────────────────┐
│  GOVERNANCE KERNEL        │              │  RETRIEVAL + INGESTION LAYER     │
│  DSC  · PAAP  · DAR       │              │  query_sql · memory_search       │
│  (deterministic, no LLM)  │◀─ scores ───│  filesystem · SharePoint · S3    │
│  LayerConfig toggles      │              │  schema mapper (table→authority)  │
│  ✓ built                  │              │  PDF/doc/image parsers            │
└──────────┬────────────────┘              │  evidence bundle assembler        │
           │ receipts + audit events       │  ✓ SQL/memory built · ✗ doc/image│
└──────────┬────────────────────────────────────────────────────────────────────┘
           │
┌──────────▼────────────────────────────────────────────────────────────────┐
│  AUDIT + EXPLAINABILITY + VERSIONING                                      │
│  audit.jsonl (append-only) · run artifacts · evidence records            │
│  authorization receipts · benchmark results                               │
│  DecisionRecord (structured) · human-readable decision memo               │
│  knowledge base snapshots · model version pinning · GDPR erasure path    │
│  ✓ audit built · ✗ DecisionRecord / snapshots / erasure not built        │
└───────────────────────────────────────────────────────────────────────────┘
           │ metrics · alerts · cost
┌──────────▼────────────────────────────────────────────────────────────────┐
│  OBSERVABILITY + COST CONTROLS                                            │
│  worker_cost events (✓) · worker latency p50 (✓)                        │
│  cross-run dashboards · failure rate alerts · cost budget per run        │
│  model gateway (rate limiting · routing · cost cap)                      │
│  secrets vault (credentials, not .env)                                   │
│  ✓ per-worker cost built · ✗ dashboard / alerts / vault not built        │
└───────────────────────────────────────────────────────────────────────────┘
```

---

### Deeper: all components and their state

```
EXPERIENCE
  browser cockpit ──── workshop floor (runs, agents, events)
                   └── governance cockpit (scope, evidence, DAR, benchmarks)
  CLI ────────────────  benchmark-config · run · list · validate-contract
  REST API ───────────  /api/runs  /api/benchmarks  /api/runs/:id/scope|evidence|authorization

REQUEST GATEWAY
  decision router ────  keyword + LLM fallback → decision_type + confidence
  domain classifier ──  procurement · story · software_build · (cv_review planned)
  clarification flow ──  underspecified tasks ask questions before architecture builds

ORCHESTRATION
  architecture registry ─  static definitions (software-scaffold-build/v1)
  proposal builder ──────  LLM → goal_structure → topology → package decomposition
  contract generator ────  packages → worker contracts (read_paths, write_paths,
                           allowed_tools, validators, output_schema, dar_action_type,
                           scope_contract, layer_config, evidence_profile)
  scheduler ─────────────  dependency graph · phase gate enforcement
                           parallel intake phases · downstream unlock on validation
  phase gate manager ────  human_gate · benchmark auto-approver

WORKER EXECUTION
  worker runner ──────────  system prompt builder · tool loop · JSON parser
                            JSON-nudge recovery · max_steps enforcement
  tool provider ───────────  read_file · write_file · list_files · run_tests
                             web_search (stub) · query_sql (built) · memory_search (built)
                             list_external_inputs · read_external_input (built)
  output validator ────────  schema validation → DSC check → PAAP scoring → DAR trigger

GOVERNANCE KERNEL  [deterministic — no LLM in path]
  DSC ─────────────  ScopeContract: allowed/required evidence classes,
                     out-of-scope markers, phrase blocklist
                     enforced at: output validation, system prompt injection
  PAAP ────────────  EvidenceSource + EvidenceRecord
                     score = authority × temporal × conflict × corroboration
                     thresholds: min_avg_score, min_individual_score
                     persists scored records to evidence/
  DAR ─────────────  ActionProposal → consequence_class lookup → decision matrix
                     ALLOW / DENY / ESCALATE — deterministic, no model
                     persists AuthorizationReceipt to authorization/
  LayerConfig ─────  toggle each layer per run (dsc · paap · dar · human_gate)
                     stored in run-record.json, threaded through all governance calls

DATA GATEWAY  [agents never connect to data sources directly]
  Rule: no worker ever holds a DB connection string, API key, or file path
        beyond what the gateway exposes as an annotated evidence excerpt.
  SchemaMapper ─────────  configs/data-sources/schema-map.json (built)
                          table/folder/API → evidence_class + authority weight
                          vendor_mgmt.proposals → vendor_proposal (0.70)
                          compliance.certifications → compliance_rule (0.95)
  query_sql tool ────────  workers call query_sql(table, filters) (built)
                          gateway checks allowed_tables (DSC), runs query,
                          annotates each row: evidence_class + timestamp + excerpt
                          agents see excerpts, never credentials
  web_fetch tool ─────── planned: governed HTTP GET through SandboxPolicy
  FileRetrieval ─────────  Drive / SharePoint / S3 → annotated documents (planned)
  ExternalToolRetrieval ─  Wrike / Jira / CRM → reference_check evidence (planned)

RETRIEVAL LAYER
  MemoryProvider ────────  search(query, scope) → list[MemoryHit]
                           scope is required — structurally enforces DSC boundary
  FilesystemMemory ──────  knowledge/ + data/memory/ (built — keyword search)
  VectorMemory ──────────  pgvector / FAISS (planned — semantic search)
  ObsidianMemory ─────────  human-edited markdown vault (planned)
  EvidenceBundleAssembler   pre-fetch evidence at run creation, score with PAAP,
                            lock into run context — workers get snapshot (planned)
  memory_search tool ────  workers call memory_search(query) (built)
                           returns past run evidence within DSC scope

MODEL PROVIDERS  [behind provider seam — kernel never imports directly]
  AnthropicProvider ───  claude-sonnet-4-6 (built)
  OllamaProvider ──────  qwen2.5 · llama3.1 via local Ollama (built)
  LocalModelProvider ───  llamacpp / MLX / MLC — on-device, never leaves phone (planned)
  MockProvider ────────  deterministic test output (built)
  FallbackProvider ────  primary → fallback chain on failure (built)

AUDIT + STORAGE
  audit.jsonl ─────────  append-only event log — complete run replay from this alone
  run-record.json ─────  layer_config · provider_override · benchmark_mode
                         execution_context · connectivity · time_model  ← new
  scope.json ──────────  DSC scope contract for the run
  evidence/*.json ─────  PAAP scored records per worker
  authorization/*.json ─  DAR receipts per action
  outputs/*.json ───────  worker structured outputs
  checkpoints/*.json ───  worker state after each tool call — enables retry from last step
  external_inputs/*.json  evidence received from outside during long-running pause
  data/benchmarks/ ─────  benchmark results · CSV · summary.json · claim_check
```

---

### Data gateway + retrieval layer — detailed

**Design rule: agents never connect to data sources directly.**
Every data access goes through the Data Gateway. Workers call tools (`query_sql`,
`web_fetch`, `memory_search`). The gateway enforces DSC scope, annotates every result
with evidence class and authority weight, and logs every access in the audit trail.
Credentials never reach the agent.

```
COMPANY INFORMATION SYSTEMS
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐
│  SQL Database    │  │  File Storage    │  │  Bucket Storage  │  │  Business Tools   │
│  (hundreds of   │  │  SharePoint      │  │  S3 / GCS        │  │  Wrike · Jira     │
│   tables)       │  │  OneDrive        │  │  Azure Blob      │  │  CRM · ERP        │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  └────────┬──────────┘
         │                    │                      │                     │
         └────────────────────┴──────────────────────┴─────────────────────┘
                                         │  raw data (credentials stay here)
                              ┌──────────▼──────────────────────────────────┐
                              │  DATA GATEWAY  (agents never bypass this)   │
                              │                                             │
                              │  Schema mapper                              │
                              │    contracts.signed_agreements → signed_contract 1.00 │
                              │    vendor_mgmt.rankings   → compliance_rule 0.95 │
                              │    vendor_mgmt.proposals  → vendor_proposal 0.70 │
                              │    market_intel.benchmarks→ market_benchmark 0.65│
                              │    jira.closed_tickets    → reference_check 0.60 │
                              │    unstructured_notes     → analyst_estimate 0.40│
                              │                                             │
                              │  Semantic layer (column descriptions)       │
                              │    unit_price_eur → "per-unit EUR excl VAT" │
                              │    iso27001_certified → "cert on file"     │
                              │                                             │
                              │  Access control                             │
                              │    allowed_tables from DSC contract scope   │
                              │    read-only: agents cannot mutate data    │
                              │    every query logged: run_id + worker_id  │
                              │    credentials in vault, never reach agents│
                              │                                             │
                              │  Annotator (stamps every row with PAAP)    │
                              │    evidence_class · authority · timestamp   │
                              │    source_id · excerpt                     │
                              └──────────┬──────────────────────────────────┘
                                         │ annotated EvidenceSource objects
                              ┌──────────▼──────────────────────────────────┐
                              │  EVIDENCE BUNDLE ASSEMBLER  (planned)       │
                              │                                             │
                              │  At run creation: fetch all required        │
                              │  evidence via gateway, PAAP-score each,    │
                              │  snapshot locked at run_created timestamp  │
                              │  Workers read snapshot — reproducible      │
                              └──────────┬──────────────────────────────────┘
                                         │ scoped, scored, timestamped bundle
                              ┌──────────▼──────────────────────────────────┐
                              │  MEMORY PROVIDER                           │
                              │  search(query, scope: DecisionScope)       │
                              │  scope is required — DSC boundary enforced │
                              │                                             │
                              │  FilesystemMemory ── knowledge/ + past runs│
                              │                      keyword search (built) │
                              │  VectorMemory ─────── pgvector / FAISS     │
                              │                       semantic (planned)   │
                              │  ObsidianMemory ────── human vault (planned)│
                              └──────────┬──────────────────────────────────┘
                                         │ MemoryHit (excerpt + evidence_class + score)
                                         ▼
                              Worker system prompt + context bundle
```

---

### Unified task model — four runtime configurations

A task is a navigation problem in decision space. The governance kernel, worker
contracts, and audit trail are **identical across all configurations**. What varies
is where compute runs, how evidence arrives, and when gates fire.

```
Task schema (three new fields unify all deployment contexts)
──────────────────────────────────────────────────────────────────
  execution_context:  "cloud"    | "mobile"         | "edge"
  connectivity:       "always_on"| "offline_first"  | "intermittent"
  time_model:         "sync"     | "async"          | "long_running"

Configuration map
──────────────────────────────────────────────────────────────────
                 Cloud/online    Long-running    Mobile/local    Robotics (future)
                 ────────────    ────────────    ────────────    ─────────────────
execution_ctx    cloud           cloud           mobile          edge
connectivity     always_on       intermittent    offline_first   always_on
time_model       sync            long_running    sync            continuous
how belief       DB query /      webhook /       grant approved  sensor stream
updates          API call        email           / web_fetch
human gate       web UI click    async notif.    phone swipe     real-time override
evidence         live query      snapshot +      SandboxPolicy   sensor bundle
arrives          at runtime      external input  grants
──────────────────────────────────────────────────────────────────

These four configurations share:
  - same worker contracts (read_paths / write_paths / allowed_tools / validators)
  - same governance kernel (DSC · PAAP · DAR · LayerConfig)
  - same audit.jsonl format (complete replay from this file in any context)
  - same evidence authority weights
  - same human gate semantics (gate_approved event before final action)
```

The thesis claim extended: not just "architecture defines behavior" but
**"the same architecture works across execution contexts without changing the
governance rules."** A worker contract written for a cloud procurement run is
executable on a phone with a local model and offline-first evidence — identical
constraints, identical audit trail, identical governance outcome.

---

### Data flow for a single governed procurement run

```
1. TASK INTAKE
   CLI / UI → task JSON
   decision_router → decision_type = "procurement"
   task carries: execution_context · connectivity · time_model

2. ARCHITECTURE
   procurement domain → funnel topology
   3 parallel intake workers → evaluator → recommender
   contracts generated with: scope_contract · evidence_profile · layer_config
                              allowed_tables · dar_action_type

3. EVIDENCE BUNDLE (planned: pre-flight; current: workers read at runtime)
   schema mapper → fetch from DB/files matching DSC scope
   PAAP scores each source
   bundle locked in run context

4. WORKER EXECUTION (parallel intake)
   requirement_analyst  ─────────────────────────────────┐
   market_scout        ─── reads evidence bundle ──────── ├── all produce structured
   risk_assessor       ─────────────────────────────────┘  │  JSON + evidence_sources
                                                            │  validated by DSC + PAAP
5. EVALUATOR
   reads all three intake outputs
   scores vendors against rubric
   evidence must be compliance_rule + vendor_proposal typed
   PAAP: record_score ≥ min_avg_score or rejected
   DAR: score_vendors → INTERNAL_REVERSIBLE → ALLOW if floor met

6. RECOMMENDER
   reads evaluator shortlist
   produces decision brief + contract conditions + human decisions required
   DAR: publish_recommendation → EXTERNAL_VISIBLE → ESCALATE
   phase gate opens → waits for human approval

7. HUMAN GATE
   human reviews: scope · evidence scores · DAR receipt · recommendation brief
   approves or rejects → gate_approved event
   on approval: evidence indexed to cross-run memory → run_completed

8. LONG-RUNNING VARIANT (time_model = "long_running")
   if evidence insufficient at step 3 or 5:
     operator calls POST /api/runs/:id/pause
     run.status → waiting_external_input
   when vendor submits proposal / legal approves / webhook fires:
     POST /api/runs/:id/external-input → evidence bundle updated
     run.status → running → evaluator resumes with new evidence
   full timeline: started 2026-05-01 · paused 2026-05-02 · resumed 2026-05-10 · approved 2026-05-11

9. AUDIT
   audit.jsonl: complete replay of every decision, tool call, governance event
   scope.json · evidence/*.json · authorization/*.json · outputs/*.json
   external_inputs/*.json · checkpoints/*.json (worker retry state)
   CSV + summary.json for benchmark comparison
```

---

## Source Layout

```text
backend/
  src/decision_agent/
    modules/          decision/runtime domain logic
    shared/           infrastructure helpers and provider seams
    cli.py            thin command interface
    server.py         thin local HTTP/static server
public/               browser UI
data/                 runtime runs, audit logs, outcomes
```

The frontend can remain Node/TypeScript later. The backend/runtime is Python because it will own
agent execution, provider adapters, validation, document/email processing, and thesis experiments.

### 1. Task Intake

Accepts a structured task document. For now this is JSON from the CLI.

### 2. Decision Router

Classifies the task into a decision type. The first supported type is:

```text
software_project_build_task
```

Future types include:

```text
personal_purchase_planning
document_update
engineering_review
cv_review
```

### 3. Architecture Registry

Stores executable architecture definitions. An architecture defines:

- decision type,
- risk level,
- required evidence,
- worker contracts,
- validators,
- action gate,
- outcome metrics.

### 4. Worker Contracts

Worker contracts are the main guardrail. A worker contract constrains a model or human worker by capability, not by trust.

Contract fields:

```json
{
  "worker_id": "decision_kernel_worker",
  "layer": "decision_kernel",
  "work_layer": "api",
  "architecture_id": "software-scaffold-build/v1",
  "goal": "Implement router and architecture registry.",
  "read_paths": ["ARCHITECTURE.md", "backend/src/**"],
  "write_paths": ["backend/src/**"],
  "allowed_tools": ["read_file", "write_file", "run_tests"],
  "max_steps": 6,
  "output_schema": {},
  "validators": ["write_scope", "schema", "tests"]
}
```

### 5. Runner

The runner instantiates an architecture for a concrete task and writes a run folder:

```text
data/runs/<run-id>/
  task.json
  run-record.json
  audit.jsonl
  contracts/
    *.json
```

### 6. Validators

Validators check architecture and contract integrity before any worker is dispatched. Later versions will also validate worker outputs and diffs.

### 7. Action Gate

The bootstrap phase has an integration gate, not automatic execution. Later phases will add gates for money, emails, purchases, repository writes, and external systems.

## What Is Built vs Missing — Layer Gap Map

Mapped against standard agentic AI reference architecture (Palantir AIP / generic reference)
plus industry requirements from empirical deployment analysis.
Legend: ✓ built · ~ partial · ✗ missing

```
LAYER                   COMPONENT                           STATUS   NOTES
──────────────────────────────────────────────────────────────────────────────────
0. IDENTITY + AUTHORIZATION   [MISSING — critical for production]
                        Authentication (SSO/OIDC/SAML)      ✗        anyone on localhost can create runs
                        Role-based access control            ✗        who can approve gate vs who can view
                        Tenant isolation                     ✗        Team A cannot see Team B's runs
                        Named audit actors                   ✗        audit log has no "who clicked approve"
                        4-eyes (multi-person gate)           ✗        one approver only; some decisions need two
                        Sequential approval workflow         ✗        legal reviews → finance approves
                        Time-limited approvals               ✗        gate approval should expire after N hours

1. ORCHESTRATION
                        Decision router                     ✓        keyword + LLM fallback
                        Domain classifier                   ✓        procurement · story · software
                        Architecture registry               ✓        static + dynamic proposal
                        Contract generator                  ✓        DSC + PAAP + DAR embedded
                        Dependency-aware scheduler          ✓        parallel intake, gate enforcement
                        Phase gate manager                  ✓        human gate + auto-approver
                        Worker retry + checkpoint           ✓        resumes from last tool call
                        Context budget management           ✗        no hard token limit per run
                        Intent clarification                ~        exists but not wired to all domains
                        Persistent job queue                ✗        runs die if server restarts
                        Long-running pause / resume         ✗        cannot pause 3 weeks for vendor RFQ
                        External webhook triggers           ✗        vendor submits → run resumes
                        Scheduled polling                   ✗        "check for response every 24h"

2. AGENTS (specialized)
                        Procurement workers (5)             ✓        requirement · market · risk · eval · recommend
                        Dynamic architecture generation     ✓        any domain via LLM proposal
                        Worker fallback + circuit breaker   ✓        retry / provider fallback built
                        Fallback agent escalation           ✗        worker fails 3× → no human escalation path
                        Communication agent                 ✗        no summariser for human-readable status
                        Capability registry                 ✗        no formal registry of agent capabilities
                        Critic agent (output quality)       ✗        is the recommendation grounded in evidence?
                        Smaller models per worker type      ✗        all workers use same model; intake could use Haiku

3. TOOLS
                        read_file / write_file / list_files ✓        path-enforced by contract
                        query_sql                           ✓        built; schema mapper + SQLite demo DB
                        memory_search                       ✓        filesystem keyword search built
                        web_search                          ~        interface exists, no real implementation
                        File/doc extraction (PDF/Excel)     ✗        not built — contracts arrive as PDF
                        Image understanding                 ✗        engineering drawings, site photos
                        SharePoint / OneDrive connector     ✗        not built
                        S3 / bucket connector               ✗        not built
                        Wrike / Jira / CRM connector        ✗        not built
                        Email ingestion                     ✗        vendor proposals arrive by email
                        Code execution sandbox              ✗        not applicable yet

4. MEMORY
                        Filesystem knowledge base           ✓        knowledge/ folders (static)
                        In-context evidence bundle          ~        workers read files; no pre-assembled bundle
                        Short-term (context window mgmt)    ✗        no token budget per worker
                        Long-term (vector DB)               ✗        no pgvector / FAISS / Chroma
                        Cross-run episodic memory           ✗        audit.jsonl per run, not queryable across runs
                        User / org profile store            ✗        behavior provider planned, not built
                        Schema mapper (DB → evidence class) ✗        config design exists, not implemented

5. GOVERNANCE KERNEL  [your differentiator — not in standard reference architectures]
                        DSC (decision scope contract)       ✓        allowed/required/blocked evidence classes
                        PAAP (evidence authority scoring)   ✓        deterministic formula, no LLM in path
                        DAR (authorization receipts)        ✓        ALLOW / DENY / ESCALATE matrix
                        LayerConfig (per-run toggles)       ✓        dsc · paap · dar · human_gate
                        Worker contracts (bounded auth)     ✓        read/write/tools/allowed_tables enforced
                        Human gate                          ✓        phase gate + gate_approve
                        Compliance-coverage frontier        ✓        benchmark sweep across PAAP thresholds
                        4-eyes multi-person gate            ✗        required_approvers per gate
                        Sequential approval workflow        ✗        legal then finance, not both at once
                        Time-limited gate approval          ✗        approval expires after 48h
                        Prompt injection guards             ✗        malicious task input can manipulate workers
                        Rate limiting on API                ✗        no protection on endpoints

6. DATA GATEWAY  [partially built — schema mapper exists; full gateway not yet]
                        Schema mapper (configs/schema-map.json) ✓   table → evidence_class + authority
                        query_sql tool with allowed_tables check ✓  enforces DSC scope at query seam
                        demo.db (SQLite) + real connector seam  ✓   SQLite built; PostgreSQL driver planned
                        Semantic data gateway (no direct conn)  ✗   agents still hold direct sqlite reference
                        Variable/column descriptions            ✗   columns need business meaning, not just names
                        Business glossary                       ✗   "unit_price_eur" = per-unit EUR excl VAT
                        Schema evolution handling           ✗        new column → update gateway, not workers
                        Row-level security                  ✗        Project A cannot see Project B's budget
                        Credential isolation                ✗        agents never see DB passwords (vault only)
                        Query translation (NL → SQL)        ✗        worker asks semantically, gateway translates
                        Read-only enforcement               ✗        workers cannot mutate data via gateway
                        Connection pooling                  ✗        100 concurrent runs → one pool
                        Evidence annotation at seam         ✓        schema-map.json maps table → evidence_class
                        Audit of every data access          ~        tool_called event exists, no structured log

7. IDENTITY + SECURITY
                        Local bind (127.0.0.1)              ✓        not network-exposed by default
                        Authentication                      ✗        no auth on /api/runs
                        Role-based access control           ✗        no who-can-what
                        Tenant isolation                    ✗        runs are not org-scoped
                        Named audit actors                  ✗        audit log has no user identity
                        PII detection at ingestion          ✗        personal data leaks into audit.jsonl
                        GDPR right-to-erasure               ✗        cannot scrub person from audit without breaking it
                        Secrets management (vault)          ✗        API keys in .env not vault
                        Purpose limitation                  ✗        HR data can flow into procurement run

8. MONITORING & OBSERVABILITY
                        Run event log (audit.jsonl)         ✓        complete replay — excellent for audit
                        Governance cockpit                  ✓        scope / evidence / DAR / benchmark views
                        Per-worker cost tracking            ✓        worker_cost event: input/output tokens
                        Per-worker latency p50              ✓        wall_time_ms in worker_cost event
                        Real-time worker status             ~        cockpit polls, no websocket push
                        Cross-run dashboards                ✗        no "failure rate by domain this week"
                        Cost alerts                         ✗        no warning when run exceeds budget
                        Distributed tracing                 ✗        which tool call took 30s?
                        Anomaly detection                   ✗        this run is 3× slower than baseline

9. RELIABILITY
                        worker_failed event                 ✓        emitted on any worker exception
                        auto_fail_when_blocked              ✓        detects dependency deadlock
                        JSON-nudge recovery                 ✓        one retry if model returns prose
                        Worker retry with checkpoint        ✓        resumes from last tool call
                        Exponential backoff + jitter        ✓        429/500/timeout → retry up to 4×
                        Circuit breaker                     ✓        opens after 3 failures, resets after 60s
                        Provider fallback chain             ✓        PROVIDER_FALLBACK env var
                        Persistent job queue                ✗        server restart loses in-flight workers
                        Dead letter / alerting              ✗        failed runs silently accumulate

10. EXPLAINABILITY + VERSIONING
                        Audit log (events)                  ✓        complete event replay
                        Evidence records + DAR receipts     ✓        traceable to source records
                        Structured DecisionRecord           ✗        why was vendor X rejected, human-readable
                        Regulatory decision memo            ✗        auto-generated brief for compliance review
                        Knowledge base snapshots            ✗        reproduce 6-month-old decision exactly
                        Model version pinning               ✗        run record stores model name, not version hash
                        GDPR erasure path                   ✗        delete person without destroying decision record

11. FOUNDATION / INFRASTRUCTURE
                        Model providers (Anthropic + Ollama) ✓       behind provider seam
                        Mock provider for tests             ✓
                        Local HTTP server                   ✓        single-process, dev-grade
                        Model gateway (cost/rate/routing)   ✗        no LiteLLM or equivalent
                        Vector DB (semantic search)         ~        stub exists, FAISS not deployed
                        Event bus / persistent queue        ✗        workers run in threads, not queued
                        Secrets vault                       ✗        .env only
                        CI/CD pipeline                      ✗        no automated test + deploy
```

---

### Priority order for what to build next

```
BUILT (thesis complete)
  Token cost tracking                  ✓  worker_cost event: input/output/latency
  Worker retry + checkpoint            ✓  resumes from last tool call
  Exponential backoff + circuit breaker✓  429/500/timeout → retry, fallback provider
  SQL connector + schema mapper        ✓  query_sql tool, schema-map.json, demo.db
  Cross-run memory                     ✓  FilesystemMemoryProvider, memory_search tool

NEXT (production-survivable)
  Data gateway (no direct DB access)   →  semantic layer, column descriptions, credentials in vault
  Persistent job queue                 →  server restart must not lose runs
  Long-running pause/resume            →  procurement takes weeks, not minutes
  PII detection at ingestion           →  before any real personal data enters the system
  Identity + RBAC                      →  who created this run, who can approve this gate

LATER (production-grade)
  PDF/image/document parsers           →  contracts arrive as PDF, specs as drawings
  SharePoint / Drive / S3 connectors   →  document ingestion from real stores
  Wrike / Jira / CRM connectors        →  reference_check evidence from live systems
  Semantic vector memory (pgvector)    →  replace keyword search with embeddings
  4-eyes authorization workflow        →  some gates need two approvers
  Structured DecisionRecord + memo     →  regulator-readable output per run
  Knowledge base snapshots             →  reproducible decisions from any date

DEFER
  Subprocess/container worker isolation →  V2 concern
  Multi-tenant DB isolation            →  single-org prototype is sufficient
  Horizontal scaling                   →  2-3 concurrent workers demonstrates the model
  Critic agent (grounding check)       →  useful but not governance-critical
```

## Relationship To NanoClaw/OpenClaw

This project borrows principles from NanoClaw/OpenClaw:

- persistent assistant mindset,
- bounded worker execution,
- isolation before trust,
- approvals for consequential actions,
- channel/runtime separation.

It does not start as a fork. The decision architecture kernel remains separate so it can later be exposed to OpenClaw/NanoClaw as a tool or plugin.
