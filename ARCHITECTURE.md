# Architecture

Decision Agent starts as a Python backend/runtime with a lightweight browser cockpit for
building the larger dynamic decision harness.

The immediate goal is narrow:

```text
coordinate bounded build agents using executable contracts
```

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

## Layers

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

## Relationship To NanoClaw/OpenClaw

This project borrows principles from NanoClaw/OpenClaw:

- persistent assistant mindset,
- bounded worker execution,
- isolation before trust,
- approvals for consequential actions,
- channel/runtime separation.

It does not start as a fork. The decision architecture kernel remains separate so it can later be exposed to OpenClaw/NanoClaw as a tool or plugin.
