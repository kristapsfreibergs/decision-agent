Next should be **make the cockpit control real backend state**, then add Claude as the first worker executor.

**Step 1: Add Real Run State**
Define run/agent statuses in Python, not hardcoded UI state.

Add states like:

```text
run: created, ready, running, waiting_human, validating, completed, failed
agent: planned, assigned, working, needs_human, blocked, submitted, validated, rejected
```

Goal: UI shows real state from backend.

**Step 2: Add Event Store**
Create append-only event records for everything visible in UI.

Events:

```text
run_created
contract_created
worker_assigned
worker_started
worker_message
worker_needs_human
human_answered
worker_submitted
validation_passed
validation_failed
gate_approved
gate_rejected
```

Goal: chat/status/history comes from events, not mock data.

**Step 3: Add API Actions**
Backend endpoints the UI can call:

```text
GET  /api/dashboard
POST /api/runs
POST /api/runs/:run_id/start
POST /api/runs/:run_id/agents/:worker_id/message
POST /api/runs/:run_id/agents/:worker_id/answer
POST /api/runs/:run_id/gate/approve
POST /api/runs/:run_id/gate/reject
```

Goal: UI becomes operator cockpit.

**Step 4: Connect UI To API**
Replace remaining hardcoded chat/status with backend data.

UI should support:
- start run
- select agent
- see contract
- see event history
- answer blocker
- approve/reject gate

Goal: you can manage a run visually.

**Step 5: Add Claude Provider**
Add provider abstraction:

```text
backend/src/decision_agent/shared/providers/
  base.py
  anthropic.py
  mock.py
```

Use `.env`:

```text
ANTHROPIC_API_KEY=...
MODEL_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-sonnet-4-5
```

Goal: Claude is executor behind contract, not special hardcoded agent.

**Step 6: Build One Real Worker Loop**
Start with `architecture_doc_worker`.

Flow:

```text
load contract
build scoped prompt
call Claude
require JSON output
validate schema
write worker result
append events
show in UI
```

Goal: one worker actually does bounded useful work.

**Step 7: Add Human Gate**
Before accepting results, require review.

Gate shows:
- worker output
- files proposed/changed
- validators
- evidence used
- risk level
- consequence note

Goal: deterministic/auditable decision control.

**Step 8: Add Second Architecture**
After software build works, add another decision type.

Best next architecture:

```text
personal_purchase_planning/v1
```

Because it matches your “buy groceries for week” example and tests external consequence gating.

**Immediate next build task**
I would implement this first:

> Event-backed run state + API actions + UI wired to real events.

Do **not** add Claude first. Without run state/events, Claude output has nowhere clean to live.