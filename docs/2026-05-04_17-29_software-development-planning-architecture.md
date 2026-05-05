---
tags:
  - decision-architecture
  - software-development
  - planning-agent
  - worker-contracts
  - auditability
status: draft
created: 2026-05-04 17:29
---

# Software Development Planning Architecture

Software development decisions need a dedicated planning architecture before worker execution.
This is not a skills file and not a prompt-only planner. It is an executable decision architecture
that produces the bounded implementation plan from which worker contracts are generated.

## Purpose

The planning architecture decides how a software task should be decomposed, sequenced, validated,
and gated before any implementation worker starts.

Flow:

```text
user task
-> decision router
-> software development planning architecture
-> planning agent output
-> worker contracts
-> execution
-> validation
-> human gate
-> outcome memory
```

## Planning Agent Responsibilities

The planning agent must:

- read the task, repository structure, architecture rules, and relevant prior outcomes
- classify the software work type, such as UI, API, backend logic, data, infra, tests, or docs
- decompose the task into bounded work packages
- assign each work package to a work layer
- define dependencies between packages
- decide which packages can run in parallel
- identify blockers and human questions before execution
- define validators and acceptance checks
- produce an auditable planning artifact

## Planning Output

The planning output must be structured enough to generate worker contracts without another model
inventing the execution shape.

Example:

```json
{
  "decision_type": "software_project_build_task",
  "architecture_id": "software-development-planning/v1",
  "work_packages": [
    {
      "id": "api-run-actions",
      "layer": "api",
      "goal": "Add audited run action endpoints.",
      "depends_on": [],
      "worker_type": "backend_worker",
      "read_paths": ["backend/src/**"],
      "write_paths": ["backend/src/**"],
      "validators": ["unit_tests", "api_shape"]
    }
  ],
  "parallel_groups": [["api-run-actions"]],
  "human_questions": [],
  "acceptance_criteria": [
    "Worker contracts are generated from the planning artifact.",
    "No worker receives repository-wide write scope.",
    "All consequential actions remain behind a gate."
  ]
}
```

## Execution Rule

Software worker contracts must be generated from the planning artifact, not directly from the
original user request.

The original task explains intent. The planning architecture decides execution topology.

## Why This Matters

The system should not only select agents by skill. It should construct the decision architecture
for the specific software task. A UI task, API task, refactor, migration, risky production change,
or documentation update may require different workers, dependencies, validators, and human gates.

## Implementation Sequence

This architecture should be implemented after the event-backed cockpit milestone in `docs/plan.md`.
The cockpit milestone must exist first because planning output, worker state, questions, and gate
decisions need somewhere auditable and visible to land.

### 1. Finish Event-Backed Cockpit

Complete the current milestone:

- derive run and agent state from audit events
- expose run action endpoints
- replace hardcoded UI agent states with backend-derived state
- replace hardcoded UI chat with backend messages/events
- support human answers and gate approve/reject actions from the UI

Completion condition:

```text
The UI can show a real run, real agent states, real messages, and audited human actions.
```

### 2. Add `software-development-planning/v1`

Create the first executable planning architecture in backend code.

Expected location:

```text
backend/src/decision_agent/modules/architectures/software_development_planning.py
```

This architecture should define:

- decision type handled by the planner
- planning agent contract
- required evidence profile
- planning output schema
- validators for planning artifacts
- human gate rules for risky plans

Completion condition:

```text
The architecture registry can return software-development-planning/v1.
```

### 3. Store Planning Artifacts

When the planning agent completes, write the structured plan into the run folder:

```text
data/runs/<run-id>/planning-artifact.json
```

Append audit events:

```text
planning_started
planning_completed
planning_failed
```

Completion condition:

```text
A run can contain a durable planning artifact that the UI and contract generator can read.
```

### 4. Generate Worker Contracts From Planning Artifact

Change software development execution so implementation workers are not generated directly from
the original user task.

New flow:

```text
task
-> decision router
-> software-development-planning/v1
-> planning-artifact.json
-> worker contracts
-> execution
```

The contract generator should use each `work_package` to create worker contracts with:

- `worker_id`
- `work_package_id`
- `layer`
- `goal`
- `depends_on`
- `read_paths`
- `write_paths`
- `allowed_tools`
- `validators`
- `output_schema`
- `completion_contract`

Completion condition:

```text
Generated worker contracts can be traced back to planning-artifact.json.
```

### 5. Show Planning In The UI

Add planning visibility to the cockpit.

The UI should show:

- planning status
- planning artifact summary
- work packages
- dependencies
- parallel groups
- human questions
- acceptance criteria
- generated worker contracts

Completion condition:

```text
The human can inspect why this worker architecture was chosen before execution starts.
```

### 6. Add Claude As Planning Agent Executor

Add model provider support only after the planning artifact and event-backed UI exist.

First real Claude-backed worker:

```text
software_planning_agent
```

Do not start by letting Claude execute implementation work. First make it produce the structured
planning artifact.

Provider files:

```text
backend/src/decision_agent/shared/providers/base.py
backend/src/decision_agent/shared/providers/anthropic.py
backend/src/decision_agent/shared/providers/mock.py
```

Completion condition:

```text
Claude can produce a planning artifact that passes schema and planning validators.
```

### 7. Execute One Work Package

After planning works, execute one small bounded work package generated from the plan.

Good first target:

```text
Add or update backend tests for one audited action endpoint.
```

Completion condition:

```text
One generated worker contract can be executed, validated, and shown in the UI.
```

### 8. Add Human Gate Review

Before accepting implementation output, require a human gate.

The gate must show:

- original task
- planning artifact
- generated worker contracts
- worker output
- validation results
- affected files
- risk level
- consequence note

Completion condition:

```text
No implementation result is accepted without an auditable approve/reject gate event.
```

## Immediate Next Action

Finish `docs/plan.md` first:

```text
event-backed run state
-> action endpoints
-> UI reads real events
```

Then start this architecture:

```text
software-development-planning/v1
```
