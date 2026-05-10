Ready for review
Select text to add comments on the plan
Plan: Long-Running Pause/Resume with External Input (V1)
Context
Real procurement decisions span days or weeks. A run starts, intake workers gather requirements and assess risk, then the system pauses waiting for vendors to submit proposals. When a vendor proposal arrives (via webhook, API call, or manual upload), the run resumes: evaluator now has the evidence it needs and scores the vendors.

Same pattern for: waiting for legal review, invoice receipt, contract signature confirmation, finance budget approval, or any external event the system cannot trigger itself.

V1 scope (explicit only): operator explicitly pauses a run; external input arrives via API; scheduler kicks once; evaluator reads new inputs via scoped tool. Automatic pause-on-insufficient-evidence, persistent job queue, and email parsing are explicitly deferred.

What Already Exists (reuse, do not rebuild)
state.py — event vocabulary, derive_run_status() — extend here
service.py — answer_worker(), post_worker_message() — pattern for event-appending functions
scheduler.py — get_ready_worker_ids(), is_run_complete() — reuse as-is
audit_log.py — append_audit_event() — the backbone
auto_approver.py — watch_run_to_completion() — partial reuse for one-shot kick
server.py — existing POST pattern for new endpoints
tools.py — execute_tool() / TOOL_DEFINITIONS — add new tools here
procurement.py — WORKER_CATALOG — update read_paths for evaluator
Revised Deliverables
Deliverable 1: State — new events, status, timeline deriver
File: modules/runs/state.py

Add event constants:

EXTERNAL_INPUT_REQUESTED = "external_input_requested"  # operator pauses run
EXTERNAL_INPUT_RECEIVED  = "external_input_received"   # evidence arrives
RUN_PAUSED               = "run_paused"                # alias for clarity
RUN_RESUMED              = "run_resumed"               # alias for clarity
Add status constant:

RUN_STATUS_WAITING_EXTERNAL = "waiting_external_input"
Extend _RUN_EVENT_TO_STATUS:

EXTERNAL_INPUT_REQUESTED: RUN_STATUS_WAITING_EXTERNAL,
RUN_PAUSED:               RUN_STATUS_WAITING_EXTERNAL,
EXTERNAL_INPUT_RECEIVED:  RUN_STATUS_RUNNING,
RUN_RESUMED:              RUN_STATUS_RUNNING,
Add derive_run_timeline(events) function — returns a list of milestone dicts derived from audit events, sorted by timestamp. No file written — computed on demand.

def derive_run_timeline(events: list[dict]) -> list[dict]:
    """Return key milestones from audit events with human-readable labels.
    
    Milestones: run_created, run_started, each worker_started, each worker_submitted,
    external_input_requested, external_input_received, gate_approved/rejected.
    """
No timeline.json file. Timeline is purely derived from audit events on read.

Deliverable 2: Service — pause, receive external input, read inputs
File: modules/runs/service.py

pause_run(run_id, reason, waiting_for, root)

Explicit pause only. Appends RUN_PAUSED + EXTERNAL_INPUT_REQUESTED events with:

{"event": EXTERNAL_INPUT_REQUESTED, "run_id": ..., "reason": ..., "waiting_for": ...}
Returns updated run. No thread management — pure event append.

receive_external_input(run_id, source_id, input_type, content, created_at, metadata, root)

Validates then persists raw input. Does NOT score evidence immediately (PAAP fires only when a worker cites it in evidence_sources at submission).

Validation rules enforced before any write:

source_id must match ^[a-zA-Z0-9_\-]{1,64}$ (path-safe, no injection)
input_type must be in the run's DSC allowed_evidence_classes (scope check)
Idempotent: if source_id already exists → raise ValueError with message. Caller must pass overwrite=True explicitly to replace.
Run must be in waiting_external_input or running status
On success:

Write data/runs/{id}/external_inputs/{source_id}.json:
{
  "source_id": "vendor_proposal_lenovo",
  "evidence_class": "vendor_proposal",
  "content": "Lenovo ThinkPad T16 Gen 3: EUR 1,799/unit...",
  "created_at": "2026-05-15",
  "received_at": "2026-05-15T14:32:00Z",
  "metadata": {"sender": "sales@lenovo.com"}
}
Append EXTERNAL_INPUT_RECEIVED event with source_id + input_type
Append RUN_RESUMED event
Return updated run (status now running)
_read_external_inputs(run_dir) helper

Add to _load_run() — reads data/runs/{id}/external_inputs/*.json sorted by received_at. Included as run["external_inputs"] in the returned run dict.

Deliverable 3: Reusable executor + external input tools
New file: modules/runs/executor.py

Extracts the scheduler loop that currently exists in two places (server.py:_run_scheduler and evaluation/runner.py:_execute_workers_in_thread) into a single reusable function:

def execute_ready_workers(
    run_id: str,
    root: Path,
    provider: LLMProvider,
    *,
    max_iterations: int = 240,
    poll_interval: float = 1.0,
) -> None:
    """Run workers as they become ready. Used by server scheduler,
    benchmark runner, and external-input resume path.
    Replaces duplicated scheduler loops."""
server.py:_run_scheduler and evaluation/runner.py:_execute_workers_in_thread both call this function. After receive_external_input() changes status to running, the API endpoint calls execute_ready_workers() in a background thread — one kick, no polling watcher.

New tools in modules/workers/tools.py

Workers cannot read external_inputs/ via read_file unless the path is in allowed_read_paths. Instead of adding a wildcard path, add two scoped tools:

# list_external_inputs: returns JSON list of available external inputs for this run
{
  "name": "list_external_inputs",
  "description": "List external inputs received for this run (vendor proposals, signed contracts, etc.). Returns source_id, evidence_class, created_at, content preview.",
  "input_schema": {"type": "object", "properties": {}}
}

# read_external_input: returns full content of one external input
{
  "name": "read_external_input",
  "description": "Read the full content of a received external input by source_id.",
  "input_schema": {
    "type": "object",
    "properties": {"source_id": {"type": "string"}},
    "required": ["source_id"]
  }
}
Implement in execute_tool():

list_external_inputs: reads data/runs/{run_id}/external_inputs/*.json, returns source_id + evidence_class + created_at + content[:200] for each
read_external_input: reads the specific file; checks source_id is path-safe; returns full content. Audit emits tool_called with source_id (no credential data)
Update procurement evaluator

In procurement.py WORKER_CATALOG, add to evaluator:

"allowed_tools": [...existing..., "list_external_inputs", "read_external_input"],
Workers can now discover and read vendor proposals without needing read_paths magic.

Deliverable 4: API endpoints
File: server.py

POST /api/runs/:run_id/pause
  Body: {"reason": "waiting for vendor proposals", "waiting_for": "vendor_proposal"}
  → calls pause_run()

POST /api/runs/:run_id/external-input
  Body: {
    "source_id":  "vendor_proposal_lenovo",
    "input_type": "vendor_proposal",
    "content":    "Lenovo ThinkPad T16 Gen 3: EUR 1,799/unit, 6-week EU delivery...",
    "created_at": "2026-05-15",
    "metadata":   {"sender": "sales@lenovo.com"},
    "overwrite":  false
  }
  → calls receive_external_input()
  → starts execute_ready_workers() in background thread
  → returns updated run record

GET /api/runs/:run_id/external-inputs
  → returns run["external_inputs"] list

GET /api/runs/:run_id/timeline
  → reads run audit, calls derive_run_timeline(events), returns list
No watch_for_external_inputs(). Resume is a single scheduler kick triggered by the API call. Server restart safety is already guaranteed: run status derives from audit.jsonl, which is file-based and persistent. After restart, a caller can re-POST to /external-input or manually call /start on a paused run.

Data layout
data/runs/{run_id}/
  audit.jsonl                           ← events including RUN_PAUSED, EXTERNAL_INPUT_RECEIVED
  run-record.json                       ← layer_config, provider_override, etc.
  external_inputs/
    vendor_proposal_lenovo.json         ← raw input, one file per source_id
    vendor_proposal_dell.json
  evidence/                             ← PAAP records — only written after worker cites source
  outputs/
    evaluator.json                      ← evaluator output citing external inputs as evidence
PAAP records are written when the evaluator worker submits output that cites the external input in its evidence_sources. Not before. This keeps DAR's evidence_floor_met() clean — external inputs only affect authorization after a worker has explicitly cited and validated them.

Run lifecycle example (explicit V1)
Day 0, 09:00
  POST /api/runs               → run_id created
  POST /api/runs/{id}/start    → intake workers run
  intake completes: requirements + market (no proposals yet) + risk
  POST /api/runs/{id}/pause    → {"waiting_for": "vendor_proposal"}
    appends RUN_PAUSED + EXTERNAL_INPUT_REQUESTED
    run.status = waiting_external_input
    evaluator stays PLANNED (deps validated but gate blocked)

Day 10, 14:32
  Vendor emails proposal → operator or webhook calls:
  POST /api/runs/{id}/external-input  → {"source_id": "vendor_proposal_lenovo", ...}
    receive_external_input():
      validates source_id + scope
      writes external_inputs/vendor_proposal_lenovo.json
      appends EXTERNAL_INPUT_RECEIVED + RUN_RESUMED
    API starts execute_ready_workers() in background thread

Day 10, 14:37  (~5 min later)
  evaluator starts
  calls list_external_inputs → sees vendor_proposal_lenovo
  calls read_external_input("vendor_proposal_lenovo") → full proposal content
  cites it as evidence_source with type="vendor_proposal"
  PAAP scores the source
  evaluator submits scored shortlist
  recommender runs
  DAR ESCALATE → gate waiting for human

Day 11
  Human approves gate
  run_completed

GET /api/runs/{id}/timeline → [
  {event: "run_created",              timestamp: "Day 0, 09:00"},
  {event: "run_started",              timestamp: "Day 0, 09:00"},
  {event: "worker_started: intake×3", timestamp: "Day 0, 09:01"},
  {event: "run_paused",               timestamp: "Day 0, 09:08"},
  {event: "external_input_received",  timestamp: "Day 10, 14:32"},
  {event: "run_resumed",              timestamp: "Day 10, 14:32"},
  {event: "worker_started: evaluator",timestamp: "Day 10, 14:33"},
  {event: "gate_approved",            timestamp: "Day 11, 10:15"},
]
Critical files
File	Change
modules/runs/state.py	4 new events, 1 new status constant, derive_run_timeline()
modules/runs/service.py	pause_run(), receive_external_input(), _read_external_inputs(), _load_run() update
modules/runs/executor.py	NEW: execute_ready_workers() extracted from server + runner
modules/workers/tools.py	list_external_inputs, read_external_input tools
server.py	4 new endpoints; scheduler loop calls executor
evaluation/runner.py	_execute_workers_in_thread() calls executor
modules/architectures/domains/procurement.py	evaluator gets 2 new allowed_tools
Verification
Create procurement run, drive intake workers to completion.
POST /pause → run status = waiting_external_input.
Restart server → GET /api/runs/{id} still shows waiting_external_input (audit replay).
POST /external-input with a vendor proposal payload → status becomes running.
Evaluator calls list_external_inputs → sees the proposal.
Evaluator calls read_external_input → reads full content.
Evaluator output cites the source as vendor_proposal type.
GET /api/runs/{id}/timeline → shows pause + resume milestones.
POST /external-input with same source_id again → returns 400 (idempotent check).
All 123+ existing tests still pass.
Deferred
Persistent job queue (Redis/Celery)
watch_for_external_inputs (long-poll watcher)
Email ingestion / PDF parsing
Automatic pause on insufficient evidence
Push notifications to external systems when run resumes