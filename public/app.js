const STATES = {
  working:    { color: "#2d8a4e", icon: "▶", label: "working" },
  blocked:    { color: "#c97a1f", icon: "⏸", label: "blocked" },
  needs_human:{ color: "#2b6fb3", icon: "?", label: "needs you" },
  thinking:   { color: "#7657b3", icon: "~", label: "thinking" },
  planned:    { color: "#828282", icon: "·", label: "planned" },
  assigned:   { color: "#828282", icon: "→", label: "assigned" },
  submitted:  { color: "#2d8a4e", icon: "↑", label: "submitted" },
  validated:  { color: "#2d8a4e", icon: "✓", label: "validated" },
  rejected:   { color: "#c43a3a", icon: "×", label: "rejected" },
  idle:       { color: "#828282", icon: "·", label: "idle" },
  done:       { color: "#2d8a4e", icon: "✓", label: "done" },
  failed:     { color: "#c43a3a", icon: "×", label: "failed" }
};

const DISCIPLINES = {
  Architecture: { color: "#171717", short: "ARCH" },
  Kernel:       { color: "#2b6fb3", short: "KERN" },
  Knowledge:    { color: "#2d8a4e", short: "KNOW" },
  Outcome:      { color: "#c97a1f", short: "OUT" },
  Validation:   { color: "#c43a3a", short: "QA" },
  Human:        { color: "#7657b3", short: "HUM" }
};

// Static display metadata per worker_id (name, avatar, discipline only — no state)
const WORKER_META = {
  architecture_doc_worker:  { name: "Atlas",  initial: "A", discipline: "Architecture", seniority: "✦" },
  decision_kernel_worker:   { name: "Kernel", initial: "K", discipline: "Kernel",       seniority: "◆" },
  knowledge_profile_worker: { name: "Sage",   initial: "S", discipline: "Knowledge",    seniority: "" },
  outcome_memory_worker:    { name: "Echo",   initial: "E", discipline: "Outcome",      seniority: "" },
  test_worker:              { name: "Quinn",  initial: "Q", discipline: "Validation",   seniority: "" },
};

// Map agent status → zone
const STATUS_ZONE = {
  planned:    "lounge_room",
  assigned:   "lounge_room",
  working:    "build",
  thinking:   "research",
  needs_human:"human_room",
  blocked:    "blocked",
  submitted:  "review",
  validated:  "lounge_room",
  rejected:   "human_room",
  idle:       "lounge_room",
  done:       "lounge_room",
  failed:     "blocked",
};

const ROOMS = [
  { id: "human_room",   label: "human room",   sub: "needs your answer", x: 2.8, y: 8,  w: 16, h: 25, className: "human" },
  { id: "meeting_room", label: "meeting room", sub: "agents talking",    x: 2.8, y: 38, w: 16, h: 25, className: "meeting" },
  { id: "lounge_room",  label: "lounge room",  sub: "idle / done",       x: 2.8, y: 68, w: 16, h: 25, className: "lounge" }
];

const ZONES = [
  { id: "research", label: "research", sub: "gathering info",     x: 31, y: 12, w: 18, h: 25 },
  { id: "compare",  label: "compare",  sub: "weighing options",   x: 52, y: 12, w: 18, h: 25 },
  { id: "decide",   label: "decide",   sub: "making the call",    x: 73, y: 12, w: 18, h: 25 },
  { id: "build",    label: "build",    sub: "writing / creating", x: 31, y: 52, w: 18, h: 25 },
  { id: "review",   label: "review",   sub: "checking work",      x: 52, y: 52, w: 18, h: 25 },
  { id: "blocked",  label: "blocked",  sub: "waiting on someone", x: 73, y: 52, w: 18, h: 25, className: "blocked" }
];

// ── state ──────────────────────────────────────────────────────────────────

let dashboard = null;
let selectedAgentId = null;
let activeFilter = "all";
let chatOpen = false;
let legendOpen = false;
let taskComposerOpen = false;
let draftTaskTitle = "";
let draftTaskDesc = "";
let taskSuggestion = null;
let taskSuggestionLoading = false;
let taskSuggestionError = "";
let clarificationAnswers = {}; // questionIndex → answer string
let architecturePanelOpen = false;

const app = document.getElementById("app");

// ── API ────────────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = { method, cache: "no-store", headers: {} };
  if (body !== undefined) {
    opts.headers["content-type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(text || `Request failed: ${path}`);
  }
  if (!res.ok || data?.error) {
    throw new Error(data?.error?.message ?? `Request failed: ${path}`);
  }
  return data;
}

// ── data helpers ───────────────────────────────────────────────────────────

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatAgo(timestamp) {
  if (!timestamp) return "no activity yet";
  const then = new Date(timestamp).getTime();
  if (!Number.isFinite(then)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

function workerLastEvent(run, workerId) {
  return (run.audit ?? []).slice().reverse().find((event) => event.worker_id === workerId) ?? null;
}

function runActivitySummary(run, agents) {
  const counts = agents.reduce((acc, agent) => {
    acc[agent.state] = (acc[agent.state] ?? 0) + 1;
    return acc;
  }, {});
  const lastEvent = (run.audit ?? []).slice().reverse().find((event) => event.timestamp) ?? null;
  const active = (counts.working ?? 0) + (counts.assigned ?? 0);
  if (active) return `${active} active · last event ${formatAgo(lastEvent?.timestamp)}`;
  if (counts.failed || counts.rejected) return `${counts.failed ?? 0} failed · last event ${formatAgo(lastEvent?.timestamp)}`;
  if (counts.planned) return `${counts.planned} waiting · last event ${formatAgo(lastEvent?.timestamp)}`;
  return `last event ${formatAgo(lastEvent?.timestamp)}`;
}

function latestRun() {
  return dashboard?.runs?.[0] ?? null;
}

function activeArchitecture() {
  const run = latestRun();
  return run?.architecture_proposal
    ?? dashboard?.architectures?.find((a) => a.id === run?.architecture_id)
    ?? dashboard?.architectures?.[0]
    ?? null;
}

function agentsFromRun(run) {
  if (!run) return [];
  const workerStatuses = run.worker_statuses ?? {};
  const generatedContracts = run.generated_contracts ?? [];
  const allContracts = generatedContracts.length ? generatedContracts : (run.contracts ?? []);

  const agents = allContracts.map((contract) => {
    const meta = WORKER_META[contract.worker_id] ?? {};
    const status = workerStatuses[contract.worker_id] ?? "planned";
    const messages = (run.worker_messages ?? {})[contract.worker_id] ?? [];
    const needsHuman = status === "needs_human";
    const isRejected = status === "rejected";
    const lastMessage = messages.length ? messages[messages.length - 1] : null;
    const lastEvent = workerLastEvent(run, contract.worker_id);
    // Find the pending question (last worker_needs_human event)
    const pendingQuestion = messages.slice().reverse().find((m) => m.event === "worker_needs_human")?.text ?? null;
    // Find the last failure reason
    const lastFailure = (run.audit ?? []).slice().reverse().find((e) => e.event === "validation_failed" && e.worker_id === contract.worker_id)?.reason ?? null;
    return {
      id: contract.worker_id,
      type: "worker",
      name: meta.name ?? contract.worker_id,
      initial: meta.initial ?? contract.worker_id[0]?.toUpperCase() ?? "?",
      discipline: meta.discipline ?? "Kernel",
      state: status,
      zone: STATUS_ZONE[status] ?? "lounge_room",
      seniority: meta.seniority ?? "",
      contract,
      task: contract.goal,
      needsAnswerFrom: needsHuman ? "you" : null,
      pendingQuestion,
      lastFailure,
      lastEvent,
      lastActivity: formatAgo(lastEvent?.timestamp),
      messages,
    };
  });


  return agents;
}

function runProgress(agents) {
  if (!agents.length) return 0;
  const weights = { validated: 1, done: 1, submitted: 0.8, working: 0.55, thinking: 0.42, needs_human: 0.28, assigned: 0.15, blocked: 0.18, planned: 0.05, idle: 0.05, rejected: 0, failed: 0 };
  const total = agents.reduce((sum, a) => sum + (weights[a.state] ?? 0), 0);
  return Math.round((total / agents.length) * 100);
}

function filterOptions(architecture) {
  const layers = (architecture?.work_layers ?? architecture?.layers ?? []).map((l) => ({
    id: `layer:${l.id}`,
    label: l.title.split(" ")[0]
  }));
  return [
    { id: "all",        label: "all" },
    { id: "needs_human",label: "needs you" },
    { id: "active",     label: "active" },
    { id: "stuck",      label: "stuck" },
    ...layers
  ];
}

function filteredAgents(agents) {
  const urgency = { needs_human: 0, rejected: 1, failed: 1, blocked: 2, working: 3, thinking: 4, assigned: 5, planned: 6, submitted: 6, validated: 7, idle: 8, done: 8 };

  let visible = agents;
  if (activeFilter === "needs_human") {
    visible = agents.filter((a) => a.state === "needs_human" || a.zone === "human_room");
  } else if (activeFilter === "active") {
    visible = agents.filter((a) => ["working", "thinking"].includes(a.state));
  } else if (activeFilter === "stuck") {
    visible = agents.filter((a) => ["blocked", "failed", "rejected"].includes(a.state));
  } else if (STATES[activeFilter]) {
    visible = agents.filter((a) => a.state === activeFilter);
  } else if (activeFilter.startsWith("layer:")) {
    const layerId = activeFilter.slice("layer:".length);
    visible = agents.filter((a) => (a.contract?.work_layer ?? a.contract?.layer) === layerId);
  }

  return [...visible].sort((a, b) => (urgency[a.state] ?? 99) - (urgency[b.state] ?? 99));
}

const ALL_AREAS = [...ROOMS, ...ZONES];

// ── layout helpers ─────────────────────────────────────────────────────────

function zoneRect(zone) {
  return `left:${zone.x}%;top:${zone.y}%;width:${zone.w}%;height:${zone.h}%`;
}

function tilePosition(index, count, zone) {
  const cols = Math.max(1, Math.min(2, Math.ceil(Math.sqrt(count))));
  const rows = Math.max(1, Math.ceil(count / cols));
  const padX = 4, padTop = 9, padBottom = 5;
  const innerW = zone.w - padX * 2;
  const innerH = zone.h - padTop - padBottom;
  const stepX = cols > 1 ? innerW / (cols - 1) : 0;
  const stepY = rows > 1 ? innerH / (rows - 1) : 0;
  return {
    x: zone.x + padX + (cols === 1 ? innerW / 2 : (index % cols) * stepX),
    y: zone.y + padTop + (rows === 1 ? innerH / 2 : Math.floor(index / cols) * stepY)
  };
}

function agentPosition(agent, agents) {
  const zone = ALL_AREAS.find((z) => z.id === agent.zone) ?? ZONES[0];
  const occupants = agents.filter((a) => a.zone === agent.zone);
  const index = Math.max(0, occupants.findIndex((a) => a.id === agent.id));
  return tilePosition(index, occupants.length, zone);
}

// ── render helpers ─────────────────────────────────────────────────────────

function avatar(agent) {
  const state = STATES[agent.state] ?? STATES.idle;
  const disc = DISCIPLINES[agent.discipline] ?? DISCIPLINES.Kernel;
  return `
    <span class="avatar">
      <span class="avatar-ring" style="border-color:${disc.color}"></span>
      <span class="avatar-circle" style="background:${state.color}">${escapeHtml(agent.initial)}</span>
      ${agent.seniority ? `<span class="avatar-seniority">${escapeHtml(agent.seniority)}</span>` : ""}
      <span class="avatar-state" style="background:${state.color}">${escapeHtml(state.icon)}</span>
    </span>`;
}

function overlayHead(title, closeId) {
  return `
    <div class="overlay-head">
      <span class="overlay-title">${escapeHtml(title)}</span>
      <button class="close" id="${closeId}">×</button>
    </div>`;
}

function renderTaskSuggestion(suggestion) {
  if (!suggestion) return "";

  // Clarification-first mode: show questions as a form, hide topology
  if (suggestion.needs_clarification) {
    const questions = suggestion.human_questions ?? [];
    const disabled = taskSuggestionLoading ? "disabled" : "";
    const ctaLabel = taskSuggestionLoading ? "thinking…" : "answer and plan";
    return `
      <section class="task-suggestion">
        <div class="section-label">clarification needed</div>
        <div class="mini">${escapeHtml(suggestion.shape_reasoning ?? suggestion.goal_structure?.reasoning ?? "")}</div>
        <div class="mini" style="margin-top:6px">shape: <b>${escapeHtml(suggestion.shape ?? suggestion.goal_structure?.shape ?? "")}</b></div>
        <div class="section-label" style="margin-top:10px">before we plan, a few questions</div>
        <div class="clarification-form">
          ${questions.map((q, i) => `
            <div class="clarification-row">
              <label class="mini">${escapeHtml(q)}</label>
              <input class="clarification-input" data-idx="${i}" value="${escapeHtml(clarificationAnswers[i] ?? "")}" placeholder="your answer…" />
            </div>`).join("")}
          <button class="small-btn" id="task-clarify-btn" ${disabled}>${escapeHtml(ctaLabel)}</button>
        </div>
      </section>`;
  }

  // Full suggestion mode
  const phases = suggestion.recommended_topology?.phases ?? [];
  const packageOutline = suggestion.package_outline ?? [];
  const shape = suggestion.shape ?? suggestion.goal_structure?.shape ?? "pipeline";
  return `
    <section class="task-suggestion">
      <div class="section-label">suggested setup</div>
      <div class="proposal-grid">
        <span>shape</span><b>${escapeHtml(shape)}</b>
        <span>architecture</span><b>${escapeHtml(suggestion.suggested_architecture_label ?? suggestion.suggested_architecture_mode ?? "dynamic")}</b>
      </div>
      <div class="mini">${escapeHtml(suggestion.shape_reasoning ?? suggestion.goal_structure?.reasoning ?? "")}</div>
      ${suggestion.modifiers?.length ? `<div class="mini" style="margin-top:4px">modifiers: ${escapeHtml(suggestion.modifiers.join(", "))}</div>` : ""}
      <div class="section-label" style="margin-top:10px">topology</div>
      <ul class="path-list">
        ${phases.map((phase) => `<li><b>${escapeHtml(phase.id)}</b> · ${escapeHtml(phase.done_means)}${phase.parallelizable ? " · parallel" : ""}</li>`).join("")}
      </ul>
      <div class="mini">${escapeHtml(suggestion.recommended_topology?.reasoning ?? "")}</div>
      <div class="section-label" style="margin-top:10px">packages</div>
      <ul class="path-list">
        ${packageOutline.map((pkg) => `<li><b>${escapeHtml(pkg.id)}</b> · ${escapeHtml(pkg.work_layer)} · phase ${escapeHtml(pkg.phase_id)}</li>`).join("")}
      </ul>
      <div class="mini">workers: ${escapeHtml(String(suggestion.worker_count_reasoning?.total_workers ?? 0))} — ${escapeHtml(suggestion.worker_count_reasoning?.reason ?? "")}</div>
      <div class="section-label" style="margin-top:10px">team</div>
      <ul class="path-list">
        ${(suggestion.suggested_team ?? []).map((worker) => `
          <li>
            <b>${escapeHtml(worker.worker_id)}</b> · ${escapeHtml(worker.role)} · phase ${escapeHtml(worker.phase_id ?? "")}
            <div class="mini">${escapeHtml(worker.goal ?? "")}</div>
          </li>`).join("")}
      </ul>
    </section>`;
}

function renderTaskComposer() {
  const disabled = taskSuggestionLoading ? "disabled" : "";
  const ctaLabel = taskSuggestionLoading ? "thinking…" : "suggest setup";
  return `
    ${taskComposerOpen ? `<div class="overlay-backdrop" id="task-backdrop"></div>` : ""}
    <aside class="task-overlay ${taskComposerOpen ? "open" : ""}">
      ${overlayHead("new task", "task-close")}
      <div class="task-overlay-body">
        <div class="section-label">task</div>
        <div class="answer-box task-form">
          <input id="new-task-title" value="${escapeHtml(draftTaskTitle)}" placeholder="what needs to be done?" />
          <textarea id="new-task-desc" placeholder="description (optional)" rows="4">${escapeHtml(draftTaskDesc)}</textarea>
          <div class="answer-box">
            <button class="small-btn" id="task-suggest-btn" ${disabled}>${escapeHtml(ctaLabel)}</button>
            ${taskSuggestion && !taskSuggestion.needs_clarification ? `<button class="small-btn arch-btn" id="task-create-btn">create run</button>` : ""}
          </div>
          ${taskSuggestionError ? `<div class="mini" style="color:var(--red)">${escapeHtml(taskSuggestionError)}</div>` : ""}
        </div>
        ${renderTaskSuggestion(taskSuggestion)}
      </div>
    </aside>`;
}

// ── render functions ───────────────────────────────────────────────────────

function renderCanvas(agents) {
  const areas = [
    ...ROOMS.map((r) => ({ ...r, baseClass: "room" })),
    ...ZONES.map((z) => ({ ...z, baseClass: "zone" }))
  ].map((area) => {
    const cls = [area.baseClass, area.className].filter(Boolean).join(" ");
    const count = agents.filter((a) => a.zone === area.id).length;
    return `
      <section class="${cls}" style="${zoneRect(area)}">
        <div class="label-tab">${escapeHtml(area.label)} <span class="count">${count}</span></div>
        <div class="sub">${escapeHtml(area.sub)}</div>
      </section>`;
  }).join("");

  const tokens = agents.map((agent) => {
    const pos = agentPosition(agent, agents);
    const selected = selectedAgentId === agent.id ? "selected" : "";
    return `
      <button class="agent agent--${escapeHtml(agent.state)} ${selected}" style="left:${pos.x}%;top:${pos.y}%" data-agent="${escapeHtml(agent.id)}">
        ${avatar(agent)}
        <span class="agent-name">${escapeHtml(agent.name)}</span>
        ${["working", "assigned"].includes(agent.state) ? `<span class="agent-note">${escapeHtml(agent.state)} · ${escapeHtml(agent.lastActivity)}</span>` : ""}
      </button>`;
  }).join("");

  return `<section class="canvas">${areas}${tokens}</section>`;
}

function renderGatePanel(run, agents) {
  if (!["validating", "waiting_human"].includes(run.status)) return "";
  // Gather submitted worker summaries from audit
  const submitted = (run.audit ?? []).filter((e) => e.event === "worker_submitted");
  const failed = (run.audit ?? []).filter((e) => e.event === "validation_failed");

  const workerRows = submitted.map((e) => {
    const agent = agents.find((a) => a.id === e.worker_id);
    const changed = (e.files_changed ?? []).join(", ") || "none";
    return `
      <div class="detail-section" style="padding:8px 0;border-bottom:1px solid var(--line)">
        <div class="mini"><b>${escapeHtml(agent?.name ?? e.worker_id)}</b> — ${escapeHtml(e.summary ?? "")}</div>
        <div class="mini" style="opacity:.6">files: ${escapeHtml(changed)}</div>
      </div>`;
  }).join("");

  const failedRows = failed.map((e) => `
    <div class="mini" style="color:#c43a3a">${escapeHtml(e.worker_id)}: ${escapeHtml(e.reason ?? "")}</div>`
  ).join("");

  return `
    <section class="detail-section hot">
      <div class="section-label">gate — review worker output</div>
      <div class="mini" style="opacity:.7">risk: ${escapeHtml(run.risk_level ?? "unknown")}</div>
      ${workerRows || `<div class="mini" style="opacity:.5">No workers submitted yet.</div>`}
      ${failedRows}
      <div class="answer-box" style="margin-top:10px">
        <input id="gate-note" placeholder="note or rejection reason..." />
        <button class="small-btn" id="gate-approve" data-run="${escapeHtml(run.run_id)}">approve</button>
        <button class="small-btn" id="gate-reject" data-run="${escapeHtml(run.run_id)}" style="background:#c43a3a">reject</button>
      </div>
    </section>`;
}

function architectureProposalStatus(run) {
  const events = run.audit ?? [];
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index].event;
    if (event === "architecture_approved") return "approved";
    if (event === "architecture_rejected") return "rejected";
    if (event === "architecture_proposal_validated") return "validated";
    if (event === "architecture_proposal_rejected") return "invalid";
    if (event === "architecture_build_started") return "building";
  }
  return run.architecture_proposal ? "proposed" : "none";
}

function hasEvent(run, eventName) {
  return (run.audit ?? []).some((event) => event.event === eventName);
}

function pendingPhaseGates(run) {
  const proposal = run.architecture_proposal;
  if (!proposal) return [];
  const gates = proposal.topology?.gates ?? [];
  if (!gates.length) return [];

  const allContracts = (run.generated_contracts?.length ? run.generated_contracts : run.contracts) ?? [];
  const statuses = run.worker_statuses ?? {};
  const audit = run.audit ?? [];

  return gates.filter((gate) => {
    const phaseId = gate.placement;
    // Already approved?
    if (audit.some((e) => e.event === "phase_gate_approved" && e.phase_id === phaseId)) return false;
    // Already rejected?
    if (audit.some((e) => e.event === "phase_gate_rejected" && e.phase_id === phaseId)) return false;
    // The phase gate only makes sense to show when previous phases are all validated
    // (i.e. some workers in the gated phase exist but deps are done)
    const gatedWorkers = allContracts.filter((c) => c.phase_id === phaseId);
    if (!gatedWorkers.length) return false;
    // All workers in the gated phase must be planned/assigned (not yet running)
    const allPlanned = gatedWorkers.every((c) => {
      const s = statuses[c.worker_id] ?? "planned";
      return s === "planned" || s === "assigned";
    });
    if (!allPlanned) return false;
    // At least one worker in a prior phase must be validated
    const priorPhaseWorkers = allContracts.filter((c) => c.phase_id !== phaseId);
    return priorPhaseWorkers.some((c) => statuses[c.worker_id] === "validated");
  });
}

function renderArchitectureProposalPanel(run) {
  if (!architecturePanelOpen) return "";

  const proposal = run.architecture_proposal;
  const status = architectureProposalStatus(run);
  const generatedContracts = run.generated_contracts ?? [];

  const inner = (() => {
    if (!proposal) {
      const building = status === "building";
      return `<div class="mini" style="opacity:.6;margin-top:6px">${building ? "designing team…" : "no proposal yet"}</div>`;
    }

    const workers = proposal.workers ?? [];
    const dependencies = proposal.dependencies ?? [];
    const approved = hasEvent(run, "architecture_approved");
    return `
      <div class="mini" style="opacity:.6">${escapeHtml(status)}</div>
      <div class="proposal-grid" style="margin-top:6px">
        <span>risk</span><b>${escapeHtml(proposal.risk_level)}</b>
        <span>workers</span><b>${workers.length}</b>
      </div>
      <div class="section-label" style="margin-top:10px">team</div>
      <ul class="path-list">
        ${workers.map((w) => `<li><b>${escapeHtml(w.worker_id)}</b> · ${escapeHtml(w.work_layer ?? w.layer)} · ${escapeHtml(w.goal)}</li>`).join("")}
      </ul>
      ${dependencies.length ? `
        <div class="section-label" style="margin-top:10px">dependencies</div>
        <ul class="path-list">
          ${dependencies.map((d) => `<li>${escapeHtml(d.from)} → ${escapeHtml(d.on)}</li>`).join("")}
        </ul>` : ""}
      ${!approved ? `
        <div class="answer-box" style="margin-top:10px">
          <button class="small-btn" id="architecture-approve" data-run="${escapeHtml(run.run_id)}">approve &amp; build team</button>
          <button class="small-btn" id="architecture-reject" data-run="${escapeHtml(run.run_id)}" style="background:#c43a3a">reject</button>
        </div>` : ""}
      ${approved && !generatedContracts.length ? `
        <div class="answer-box" style="margin-top:8px">
          <button class="small-btn" id="generate-contracts" data-run="${escapeHtml(run.run_id)}">generate contracts</button>
        </div>` : ""}
      ${generatedContracts.length ? `
        <div class="answer-box" style="margin-top:8px">
          <button class="small-btn" id="schedule-run" data-run="${escapeHtml(run.run_id)}">▶ run all</button>
        </div>
        ${pendingPhaseGates(run).map((gate) => `
          <div class="detail-section hot" style="margin-top:10px;padding:8px">
            <div class="section-label">phase gate — ${escapeHtml(gate.placement)}</div>
            <div class="mini" style="opacity:.8;margin:4px 0">${escapeHtml(gate.rule ?? "Human approval required before this phase.")}</div>
            <div class="answer-box" style="margin-top:6px">
              <button class="small-btn phase-gate-approve" data-run="${escapeHtml(run.run_id)}" data-phase="${escapeHtml(gate.placement)}">approve phase</button>
              <button class="small-btn phase-gate-reject" data-run="${escapeHtml(run.run_id)}" data-phase="${escapeHtml(gate.placement)}" style="background:#c43a3a">reject phase</button>
            </div>
          </div>`).join("")}
        <div class="section-label" style="margin-top:10px">contracts</div>
        <ul class="path-list">
          ${generatedContracts.map((c) => `<li><b>${escapeHtml(c.worker_id)}</b> · ${escapeHtml((c.write_paths ?? []).join(", "))}</li>`).join("")}
        </ul>` : ""}`;
  })();

  return `
    <aside class="arch-panel open">
      <div class="overlay-head">
        <div class="detail-name" style="font-size:13px">team plan</div>
        <button class="close" id="arch-panel-close">×</button>
      </div>
      <div style="padding:10px 14px;overflow-y:auto;flex:1">${inner}</div>
    </aside>`;
}

function renderDetails(agent, run, architecture, allAgents = []) {
  if (!agent) return `<aside class="details-overlay"></aside>`;

  const state = STATES[agent.state] ?? STATES.idle;
  const disc = DISCIPLINES[agent.discipline] ?? DISCIPLINES.Kernel;
  const contract = agent.contract ?? {};

  return `
    <aside class="details-overlay open">
      <div class="overlay-head">
        ${avatar(agent)}
        <div class="detail-main">
          <div class="detail-name">${escapeHtml(agent.name)}</div>
          <div class="detail-role">${escapeHtml(disc.short)} · ${escapeHtml(contract.layer ?? agent.zone)}</div>
          <div class="mini">${escapeHtml(state.label)} · ${escapeHtml(agent.lastActivity)}</div>
        </div>
        <button class="close" id="clear-selection">×</button>
      </div>

      ${agent.state === "needs_human" ? `
      <section class="detail-section hot">
        <div class="section-label">question for you</div>
        <div style="margin:8px 0;font-size:14px">${escapeHtml(agent.pendingQuestion ?? agent.task)}</div>
        <div class="answer-box">
          <input id="answer-input" placeholder="your answer…" />
          <button class="small-btn" id="answer-send" data-run="${escapeHtml(run.run_id)}" data-worker="${escapeHtml(agent.id)}">send</button>
        </div>
      </section>` : `
      <section class="detail-section ${agent.state === "rejected" ? "blocked" : ""}">
        <div class="section-label">currently</div>
        ${["working", "assigned"].includes(agent.state) ? `
          <div class="activity-strip">running · last activity ${escapeHtml(agent.lastActivity)}</div>` : ""}
        <div class="mini">${escapeHtml(agent.task)}</div>
        ${agent.state === "rejected" && agent.lastFailure ? `
          <div class="mini" style="color:var(--red);margin-top:6px">${escapeHtml(agent.lastFailure)}</div>` : ""}
        ${["planned", "assigned", "ready"].includes(agent.state) ? `
          <div class="answer-box" style="margin-top:8px">
            <button class="small-btn" id="execute-worker" data-run="${escapeHtml(run.run_id)}" data-worker="${escapeHtml(agent.id)}">▶ execute</button>
          </div>` : ""}
        ${agent.state === "rejected" ? `
          <div class="answer-box" style="margin-top:8px">
            <button class="small-btn" id="execute-worker" data-run="${escapeHtml(run.run_id)}" data-worker="${escapeHtml(agent.id)}">↺ retry</button>
          </div>` : ""}
      </section>`}

      ${agent.messages?.length ? `
      <section class="detail-section">
        <div class="section-label">messages</div>
        ${agent.messages.map((m) => `
          <div class="detail-message ${m.role === "human" ? "detail-message--human" : ""}">
            <span class="chat-time">${escapeHtml((m.timestamp ?? "").slice(11, 16))}</span>
            <span>${escapeHtml(m.text ?? m.answer ?? "")}</span>
          </div>`).join("")}
      </section>` : ""}

      ${renderGatePanel(run, allAgents)}

      <section class="detail-section">
        <div class="section-label">write scope</div>
        <ul class="path-list">
          ${(contract.write_paths ?? []).map((p) => `<li>${escapeHtml(p)}</li>`).join("") || "<li>none</li>"}
        </ul>
      </section>

      <section class="detail-section">
        <div class="section-label">team & architecture</div>
        <button class="small-btn" id="show-architecture" style="margin-top:4px">view team plan</button>
      </section>
    </aside>`;
}

function renderChat(run, agents) {
  const messages = run.worker_messages ?? {};
  const workerById = new Map(agents.map((a) => [a.id, a]));

  const lines = [];
  for (const [workerId, msgs] of Object.entries(messages)) {
    const agent = workerById.get(workerId);
    for (const m of msgs) {
      lines.push({ agent, event: m.event, time: (m.timestamp ?? "").slice(11, 16), text: m.text ?? m.answer ?? "" });
    }
  }
  lines.sort((a, b) => (a.time > b.time ? 1 : -1));

  function nameTag(agent) {
    if (!agent) return "<b>system</b>";
    const color = (STATES[agent.state] ?? STATES.idle).color;
    return `<button class="chat-name" data-agent="${escapeHtml(agent.id)}" style="--agent-color:${color}">${escapeHtml(agent.name)}</button>`;
  }

  const linesHtml = lines.length
    ? lines.map((l) => `
        <div class="chat-line">
          <span class="chat-time">${escapeHtml(l.time)}</span>
          ${nameTag(l.agent)}
          <span class="chat-arrow">→</span>
          <span class="${l.event === "human_answered" ? "chat-human" : ""}">${escapeHtml(l.text)}</span>
        </div>`).join("")
    : `<div class="chat-line" style="opacity:.5">No messages yet.</div>`;

  return `
    <div class="chat-bar">
      <button class="chat-tab" id="chat-toggle">▸ agent chat (${lines.length})</button>
    </div>
    ${chatOpen ? `<div class="overlay-backdrop" id="chat-backdrop"></div>` : ""}
    <aside class="chat-overlay ${chatOpen ? "open" : ""}">
      ${overlayHead("agent chat", "chat-close")}
      <div class="chat-overlay-lines">${linesHtml}</div>
      <div class="chat-compose">
        <input id="broadcast-input" placeholder="broadcast or @name to address one..." />
        <button id="broadcast-send">send</button>
      </div>
    </aside>`;
}

function renderLegend() {
  function grid(entries) {
    return `<div class="legend-grid">${entries.map(([icon, label]) => `
      <span class="legend-dot-item">${icon}</span>
      <span>${escapeHtml(label)}</span>`).join("")}</div>`;
  }

  return `
    <aside class="legend-overlay ${legendOpen ? "open" : ""}">
      ${overlayHead("legend", "legend-close")}
      <div class="legend-overlay-body">
        <div class="section-label">agent status</div>
        ${grid(Object.values(STATES).map((s) =>
          [`<span class="legend-dot" style="background:${s.color}"></span> ${escapeHtml(s.icon)}`, s.label]))}

        <div class="section-label" style="margin-top:16px">discipline (avatar ring)</div>
        ${grid(Object.entries(DISCIPLINES).map(([name, d]) =>
          [`<span class="legend-dot" style="background:white;border:2.5px solid ${d.color}"></span> ${escapeHtml(d.short)}`, name]))}

        <div class="section-label" style="margin-top:16px">seniority badge</div>
        ${grid([["<b>✦</b>", "architect / human gate"], ["<b>◆</b>", "lead"]])}

        <div class="section-label" style="margin-top:16px">zones</div>
        ${grid(ALL_AREAS.map((z) =>
          [`<span class="legend-dot" style="background:var(--paper-2);border:1.5px dashed var(--line)"></span>`, `${z.label} — ${z.sub}`]))}
      </div>
    </aside>`;
}

function renderMission(run, architecture, agents) {
  const progress = runProgress(agents);
  const goal = run.task?.goal ?? run.task?.title ?? run.task?.description ?? architecture?.purpose ?? "Decision run";
  const canStart = run.status === "ready";
  const proposalStatus = architectureProposalStatus(run);
  const generatedCount = run.generated_contracts?.length ?? 0;
  const activity = runActivitySummary(run, agents);
  return `
    <section class="mission">
      <div class="goal-line">
        <span class="goal-label">GOAL</span>
        <span class="goal-title">${escapeHtml(goal)}</span>
        <span class="goal-progress"><span style="width:${progress}%"></span><b>${progress}%</b></span>
        <span class="run-status">${escapeHtml(run.status)} · ${escapeHtml(activity)}</span>
        <button class="small-btn arch-btn" id="architecture-open" data-run="${escapeHtml(run.run_id)}">architecture ${escapeHtml(proposalStatus)}${generatedCount ? ` · ${generatedCount} contracts` : ""}</button>
      </div>
      <div class="control-row">
        ${filterOptions(architecture).map((f) =>
          `<button class="chip ${activeFilter === f.id ? "active" : ""}" data-filter="${escapeHtml(f.id)}">${escapeHtml(f.label)}</button>`
        ).join("")}
      </div>
    </section>`;
}

// ── main render ────────────────────────────────────────────────────────────

function render() {
  const run = latestRun();
  const architecture = activeArchitecture();
  const allAgents = agentsFromRun(run);
  const agents = filteredAgents(allAgents);

  if (!run) {
    taskComposerOpen = true;
    app.innerHTML = `
      <div class="floor-app">
        <header class="topbar">
          <div class="brand"><div class="logo">agents.</div><div class="subtitle">workshop floor</div></div>
        </header>
        <main class="canvas" style="margin:10px">
          <div style="padding:32px;max-width:680px">
            <div class="section-label" style="margin-bottom:10px">task intake</div>
            <div class="mini" style="max-width:560px">
              Describe the work first. The system will suggest decision type, team, and workflow before it creates a run.
            </div>
          </div>
        </main>
        ${renderTaskComposer()}
      </div>`;
    bindTaskComposerEvents();
    return;
  }

  const needsYou = allAgents.filter((a) => a.zone === "human_room").length;

  app.innerHTML = `
    <div class="floor-app">
      <header class="topbar">
        <div class="brand">
          <div class="logo">agents.</div>
          <div class="subtitle">workshop floor</div>
        </div>
        <div class="top-actions">
          <button class="small-btn" id="new-task-btn" style="margin-right:8px">+ new task</button>
          <div class="pill">↔ ${allAgents.length} agents</div>
          <div class="pill"><span class="pill-dot"></span>${needsYou} need you</div>
          <button class="legend-btn" id="legend-toggle">?</button>
        </div>
      </header>

      ${renderMission(run, architecture, allAgents)}

      <main class="stage">
        ${renderCanvas(agents)}
      </main>

      ${selectedAgentId ? `<div class="overlay-backdrop" id="overlay-backdrop"></div>` : ""}
      ${renderDetails(selectedAgent(allAgents), run, architecture, allAgents)}
      ${renderArchitectureProposalPanel(run)}
      ${renderTaskComposer()}
      ${legendOpen ? `<div class="overlay-backdrop" id="legend-backdrop"></div>` : ""}
      ${renderLegend()}
      ${renderChat(run, allAgents)}
    </div>`;

  on("[data-agent]",  "click", (el) => { selectedAgentId = el.dataset.agent; architecturePanelOpen = false; render(); });
  on("[data-filter]", "click", (el) => { activeFilter = el.dataset.filter;   render(); });
  on("#clear-selection",   "click", () => { selectedAgentId = null; architecturePanelOpen = false; render(); });
  on("#show-architecture", "click", () => { architecturePanelOpen = true; render(); });
  on("#arch-panel-close",  "click", () => { architecturePanelOpen = false; render(); });
  on("#overlay-backdrop",  "click", () => { selectedAgentId = null; architecturePanelOpen = false; render(); });
  on("#legend-toggle", "click", () => { legendOpen = true;   render(); });
  on("#legend-close",  "click", () => { legendOpen = false;  render(); });
  on("#legend-backdrop","click",() => { legendOpen = false;  render(); });
  on("#chat-toggle",   "click", () => { chatOpen = true;     render(); });
  on("#chat-close",    "click", () => { chatOpen = false;    render(); });
  on("#chat-backdrop", "click", () => { chatOpen = false;    render(); });

  on("#new-task-btn", "click", () => {
    taskComposerOpen = true;
    taskSuggestion = null;
    taskSuggestionError = "";
    render();
  });

  // Open architecture controls in the team plan panel
  on("#architecture-open", "click", () => {
    architecturePanelOpen = true;
    render();
  });

  // Build dynamic architecture proposal
  on("#architecture-build", "click", async (el) => {
    el.disabled = true;
    el.textContent = "building…";
    await api("POST", `/api/runs/${el.dataset.run}/architecture/build`);
    await load();
  });

  // Approve dynamic architecture proposal — then immediately generate contracts
  on("#architecture-approve", "click", async (el) => {
    const runId = el.dataset.run;
    el.disabled = true;
    el.textContent = "generating team…";
    try {
      await api("POST", `/api/runs/${runId}/architecture/approve`, { note: "" });
      await api("POST", `/api/runs/${runId}/architecture/generate-contracts`);
    } catch (err) {
      el.disabled = false;
      el.textContent = "approve & build team";
      alert(`Failed to generate team: ${err?.message ?? err}`);
    }
    await load();
  });

  // Reject dynamic architecture proposal
  on("#architecture-reject", "click", async (el) => {
    const reason = document.getElementById("architecture-note")?.value ?? "";
    await api("POST", `/api/runs/${el.dataset.run}/architecture/reject`, { reason });
    await load();
  });

  // Generate contracts from approved architecture proposal
  on("#generate-contracts", "click", async (el) => {
    el.disabled = true;
    el.textContent = "generating…";
    try {
      await api("POST", `/api/runs/${el.dataset.run}/architecture/generate-contracts`);
    } catch (err) {
      el.disabled = false;
      el.textContent = "generate contracts";
      alert(`Failed: ${err?.message ?? err}`);
    }
    await load();
  });

  // Start run
  on("#start-run", "click", async (el) => {
    await api("POST", `/api/runs/${el.dataset.run}/start`);
    await load();
  });

  // Execute worker
  on("#execute-worker", "click", async (el) => {
    el.disabled = true;
    el.textContent = "running…";
    await api("POST", `/api/runs/${el.dataset.run}/agents/${el.dataset.worker}/execute`);
    await load();
  });

  // Schedule all ready workers in dependency order
  on("#schedule-run", "click", async (el) => {
    el.disabled = true;
    el.textContent = "scheduling…";
    await api("POST", `/api/runs/${el.dataset.run}/schedule`);
    await load();
  });

  // Answer worker blocker
  on("#answer-send", "click", async (el) => {
    const input = document.getElementById("answer-input");
    const answer = input?.value?.trim();
    if (!answer) return;
    await api("POST", `/api/runs/${el.dataset.run}/agents/${el.dataset.worker}/answer`, { answer });
    await load();
  });

  // Gate approve
  on("#gate-approve", "click", async (el) => {
    const note = document.getElementById("gate-note")?.value ?? "";
    await api("POST", `/api/runs/${el.dataset.run}/gate/approve`, { note });
    await load();
  });

  // Gate reject
  on("#gate-reject", "click", async (el) => {
    const reason = document.getElementById("gate-note")?.value ?? "";
    await api("POST", `/api/runs/${el.dataset.run}/gate/reject`, { reason });
    await load();
  });

  // Phase gate approve (mid-run, does not complete the run)
  on(".phase-gate-approve", "click", async (el) => {
    el.disabled = true;
    el.textContent = "approving…";
    try {
      await api("POST", `/api/runs/${el.dataset.run}/phase-gate/approve`, { phase_id: el.dataset.phase });
    } catch (err) {
      alert(`Failed to approve phase gate: ${err?.message ?? err}`);
    }
    await load();
  });

  // Phase gate reject (mid-run)
  on(".phase-gate-reject", "click", async (el) => {
    const reason = prompt("Reason for rejecting this phase?") ?? "";
    try {
      await api("POST", `/api/runs/${el.dataset.run}/phase-gate/reject`, { phase_id: el.dataset.phase, reason });
    } catch (err) {
      alert(`Failed to reject phase gate: ${err?.message ?? err}`);
    }
    await load();
  });

  bindTaskComposerEvents();
}

function selectedAgent(agents) {
  if (!selectedAgentId) return null;
  return agents.find((a) => a.id === selectedAgentId) ?? null;
}

function on(selector, event, handler) {
  for (const el of document.querySelectorAll(selector)) {
    el.addEventListener(event, () => handler(el));
  }
}

function bindTaskComposerEvents() {
  on("#task-close", "click", () => {
    taskComposerOpen = false;
    render();
  });
  on("#task-backdrop", "click", () => {
    taskComposerOpen = false;
    render();
  });
  on("#task-suggest-btn", "click", async (el) => {
    const titleInput = document.getElementById("new-task-title");
    const descInput = document.getElementById("new-task-desc");
    draftTaskTitle = titleInput?.value?.trim() ?? "";
    draftTaskDesc = descInput?.value?.trim() ?? "";
    if (!draftTaskTitle) return;
    taskSuggestionLoading = true;
    taskSuggestionError = "";
    clarificationAnswers = {};
    render();
    try {
      taskSuggestion = await api("POST", "/api/task-suggestions", {
        title: draftTaskTitle,
        description: draftTaskDesc,
      });
    } catch (error) {
      taskSuggestionError = error?.message ?? "Could not suggest setup.";
    } finally {
      taskSuggestionLoading = false;
      render();
    }
  });
  on("#task-clarify-btn", "click", async () => {
    // Collect answers from clarification inputs
    document.querySelectorAll(".clarification-input").forEach((input) => {
      const idx = parseInt(input.dataset.idx, 10);
      clarificationAnswers[idx] = input.value.trim();
    });
    const answers = Object.keys(clarificationAnswers)
      .sort((a, b) => Number(a) - Number(b))
      .map((k) => clarificationAnswers[k])
      .filter(Boolean);
    taskSuggestionLoading = true;
    taskSuggestionError = "";
    render();
    try {
      taskSuggestion = await api("POST", "/api/task-suggestions/refine", {
        task: { title: draftTaskTitle, description: draftTaskDesc },
        answers,
      });
    } catch (error) {
      taskSuggestionError = error?.message ?? "Could not refine setup.";
    } finally {
      taskSuggestionLoading = false;
      render();
    }
  });
  on("#task-create-btn", "click", async (el) => {
    draftTaskTitle = document.getElementById("new-task-title")?.value?.trim() ?? draftTaskTitle;
    draftTaskDesc = document.getElementById("new-task-desc")?.value?.trim() ?? draftTaskDesc;
    if (!draftTaskTitle) return;
    const steps = ["creating run…", "starting…", "planning architecture…", "done"];
    let step = 0;
    const tick = () => { el.disabled = true; el.textContent = steps[step++] ?? steps[steps.length - 1]; };
    tick();
    try {
      const run = await api("POST", "/api/runs", { title: draftTaskTitle, description: draftTaskDesc });
      tick();
      await api("POST", `/api/runs/${run.run_id}/start`);
      tick();
      const artifact = taskSuggestion?._artifact ?? null;
      await api("POST", `/api/runs/${run.run_id}/architecture/build`, artifact ? { artifact } : undefined);
      tick();
      selectedAgentId = null;
      taskComposerOpen = false;
      taskSuggestion = null;
      taskSuggestionError = "";
      clarificationAnswers = {};
      draftTaskTitle = "";
      draftTaskDesc = "";
      await load();
    } catch (err) {
      el.disabled = false;
      el.textContent = "create run";
      taskSuggestionError = err?.message ?? "Failed to create run.";
      render();
    }
  });
  const titleInput = document.getElementById("new-task-title");
  if (titleInput) {
    titleInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        document.getElementById("task-suggest-btn")?.click();
      }
    });
  }
}

// ── boot ───────────────────────────────────────────────────────────────────

async function load() {
  const response = await fetch("/api/dashboard", { cache: "no-store" });
  dashboard = await response.json();
  render();
}

let loadingDashboard = false;
async function refreshDashboard() {
  if (loadingDashboard) return;
  loadingDashboard = true;
  try {
    await load();
  } finally {
    loadingDashboard = false;
  }
}

load().catch((err) => {
  app.innerHTML = `<pre>${escapeHtml(err.stack ?? err.message)}</pre>`;
});

setInterval(() => {
  refreshDashboard().catch(() => {});
}, 2500);
