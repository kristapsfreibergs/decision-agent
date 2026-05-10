# Mobile Sandbox Architecture — Local Model, User-Controlled Access

Date: 2026-05-10
Status: Architecture design — not yet implemented
Related: [ARCHITECTURE.md](../ARCHITECTURE.md) · [literature/2026-05-09_architecture_principles_and_tradeoffs.md](../literature/2026-05-09_architecture_principles_and_tradeoffs.md)

---

## Overview

The phone runs a local LLM that never leaves the device. By default, the agent has access
to nothing except its own general knowledge (model weights). The user grants access
one-by-one: a specific folder, a specific URL, a specific file to ingest. Each grant is
logged in the audit trail. Web connections require explicit grant AND (for data-out)
governance gate approval.

This is **capability-based access control**: default-deny, explicit allowlist, per-resource.

The governance kernel (DSC, PAAP, DAR) runs entirely on-device. The model never leaves the phone.
Web connections are optional and always user-approved.

---

## Core concept: SandboxPolicy

A single JSON file stored encrypted on the device. The agent reads it at run creation to
derive its DSC scope. Nothing is allowed that is not in this file.

```json
{
  "version": 1,
  "base_knowledge_path": "/app/knowledge/",
  "grants": [
    {
      "grant_id": "g001",
      "type": "read_folder",
      "path": "/Documents/contracts/",
      "granted_at": "2026-05-10T14:32:00Z",
      "expires_at": null,
      "granted_by": "user"
    },
    {
      "grant_id": "g002",
      "type": "web_read",
      "url": "https://vendor-registry.example.com",
      "evidence_class": "vendor_proposal",
      "granted_at": "2026-05-10T14:35:00Z",
      "expires_at": "2026-06-10T14:35:00Z"
    },
    {
      "grant_id": "g003",
      "type": "file_ingest",
      "path": "/Downloads/lenovo_proposal.pdf",
      "granted_at": "2026-05-10T14:40:00Z",
      "expires_after_use": true
    }
  ]
}
```

### Grant types

| Type | What it allows | Notes |
|---|---|---|
| `read_folder` | Agent reads all files in this path | Persistent until revoked |
| `read_file` | Single file access | Persistent until revoked |
| `file_ingest` | One-time ingestion of a specific file | Self-destructs after first use |
| `web_read` | Fetch content from this URL (data flows in) | Evidence annotated with evidence_class |
| `web_write` | Send data to this URL (data flows out) | ALWAYS requires DAR gate approval |

---

## Architecture components

### SandboxPolicy module

**New file: `shared/sandbox/policy.py`**

```python
@dataclass(frozen=True)
class SandboxGrant:
    grant_id: str
    type: str           # read_folder | read_file | file_ingest | web_read | web_write
    path: str | None    # for file grants
    url: str | None     # for web grants
    evidence_class: str | None  # authority hint for web_read sources
    granted_at: str
    expires_at: str | None
    expires_after_use: bool = False

@dataclass(frozen=True)
class SandboxPolicy:
    base_knowledge_path: str    # always readable — model's general knowledge
    grants: tuple[SandboxGrant, ...]

    def to_dsc_scope(self, run_id: str, domain: str) -> ScopeContract:
        """Derive a DSC ScopeContract from active grants."""

    def allowed_read_paths(self) -> list[str]:
        return [self.base_knowledge_path] + [
            g.path for g in self.grants
            if g.type in {"read_folder", "read_file", "file_ingest"}
            and not self._expired(g)
        ]

    def allowed_web_reads(self) -> list[str]:
        return [g.url for g in self.grants
                if g.type == "web_read" and not self._expired(g)]

    def consume_ingest_grant(self, path: str) -> "SandboxPolicy":
        """Return a new policy with the file_ingest grant for this path removed."""
```

**New file: `shared/sandbox/storage.py`**

```python
def load_policy(policy_path: Path) -> SandboxPolicy:
    """Load SandboxPolicy from encrypted JSON. On mobile: decrypt with device keystore."""

def save_policy(policy: SandboxPolicy, policy_path: Path) -> None:
    """Save policy. Writes audit event: policy_updated."""

def add_grant(policy_path: Path, grant: SandboxGrant) -> SandboxPolicy:
    """Add one grant, persist, emit policy_grant_added audit event."""

def revoke_grant(policy_path: Path, grant_id: str) -> SandboxPolicy:
    """Remove a grant, persist, emit policy_grant_revoked audit event."""
```

---

### Integration with existing governance

**`create_run()` in `service.py`**

When `sandbox_policy` is provided to `create_run()`:
1. Derive DSC scope from policy: `policy.to_dsc_scope(run_id, domain)`
2. Set `allowed_read_paths` on every worker contract from policy
3. Store `sandbox_policy_version` in run-record.json for reproducibility
4. Emit `sandbox_applied` audit event with grant_ids active at run creation

**`instantiate_generated_contract()` in `generator.py`**

Accept optional `sandbox_policy: SandboxPolicy`. Override contract read_paths with
`policy.allowed_read_paths()`. No contract can read beyond what the policy allows —
even if the domain catalog declares broader read_paths.

**DAR consequence classes for web actions (`dar.py`)**

```python
CONSEQUENCE_WEB_READ  = "WEB_READ"   # data flows in from web
CONSEQUENCE_WEB_WRITE = "WEB_WRITE"  # data flows out to web
```

Decision matrix:
```
WEB_READ  + url in sandbox.allowed_web_reads  →  ALLOW
WEB_READ  + url NOT in sandbox                →  DENY  (not granted)
WEB_WRITE + any                               →  ESCALATE  (always gate; data leaving device)
```

---

### New tools: web_fetch, list_grants, request_grant

**`modules/workers/tools.py`**

```python
# web_fetch — governed HTTP GET, DAR evaluated before any network call
{
  "name": "web_fetch",
  "description": "Fetch content from a URL that has been granted in the sandbox policy.",
  "input_schema": {
    "type": "object",
    "properties": {
      "url": {"type": "string"},
      "evidence_class": {"type": "string"}
    },
    "required": ["url"]
  }
}

# list_grants — show the worker what it has access to
{
  "name": "list_grants",
  "description": "List folders, files, and URLs the current sandbox allows.",
  "input_schema": {"type": "object", "properties": {}}
}

# request_grant — worker asks user for access to something not yet granted
{
  "name": "request_grant",
  "description": "Ask the user to grant access to a path or URL.",
  "input_schema": {
    "type": "object",
    "properties": {
      "type":     {"type": "string", "enum": ["read_folder","read_file","file_ingest","web_read"]},
      "resource": {"type": "string"},
      "reason":   {"type": "string"}
    },
    "required": ["type", "resource", "reason"]
  }
}
```

**`web_fetch` execution flow:**
1. Check URL against `sandbox.allowed_web_reads()` → if absent: ERROR (not granted)
2. Build ActionProposal: action_type="web_fetch", consequence=WEB_READ
3. DAR evaluates → ALLOW or DENY
4. If ALLOW: HTTP GET → return annotated EvidenceSource:
   ```json
   {"type": "market_benchmark", "excerpt": "...", "created_at": "<fetched_at>",
    "source_url": "https://...", "grant_id": "g002"}
   ```
5. Audit: `tool_called` with url + grant_id (never the content)

**`request_grant` execution flow:**
1. Emits `grant_requested` event
2. Run enters `waiting_external_input`
3. User taps Allow → `add_grant()` → `grant_approved` event → run resumes
4. User taps Deny → `grant_denied` event → worker receives ERROR response

---

### Local model provider

**New file: `shared/providers/local.py`**

```python
class LocalModelProvider(LLMProvider):
    """Runs a quantized LLM fully on-device. Never makes network calls.

    Backends (LOCAL_MODEL_BACKEND env var):
      mlx      — Apple MLX (iOS/macOS, M-series Neural Engine, ~20 tok/s)
      llamacpp — llama.cpp (Android, cross-platform, most compatible)
      mlc      — MLC-LLM (universal, both platforms)
    """
    def __init__(self,
        model_path: str,
        backend: str = "llamacpp",
        context_window: int = 4096,
        max_tokens: int = 1024,
    ) -> None: ...
```

Registry (`shared/providers/registry.py`):
```python
if name == "local" or name.startswith("local/"):
    from decision_agent.shared.providers.local import LocalModelProvider
    return LocalModelProvider(
        model_path=os.environ.get("LOCAL_MODEL_PATH", "models/default.gguf"),
        backend=os.environ.get("LOCAL_MODEL_BACKEND", "llamacpp"),
    )
```

---

### API endpoints for grant management

```
GET    /api/sandbox/grants               list active grants
POST   /api/sandbox/grants               add a grant
         body: {"type": "read_folder", "path": "/Documents/contracts/"}
DELETE /api/sandbox/grants/:id           revoke a grant

GET    /api/sandbox/requests             list pending grant requests (from workers)
POST   /api/sandbox/requests/:id/approve user approves
POST   /api/sandbox/requests/:id/deny    user denies
```

---

## Data layout on device

```
/app/
  knowledge/                    ← always readable (general knowledge)
    procurement-rules.md
  models/
    llama-3-8b-q4.gguf          ← model weights, never leave device
  data/
    sandbox-policy.json.enc     ← encrypted sandbox policy
    runs/{run_id}/
      audit.jsonl               ← includes grant_requested, grant_approved events
      run-record.json
      outputs/  evidence/
    memory/procurement/         ← cross-run memory, on-device only

/user-data/                     ← user files, outside app sandbox
  Documents/contracts/          ← accessible only after read_folder grant
  Downloads/lenovo_proposal.pdf ← accessible only after file_ingest grant
```

---

## Recommended technologies by platform

### iOS (iPhone 15 Pro+ / Apple Silicon)

| Component | Technology | Why |
|---|---|---|
| Local LLM | MLX + Llama 3 8B Q4 | Apple's own framework, Neural Engine, ~20 tok/s |
| Governance kernel | Swift (translate from Python) | ~500 lines of pure math |
| Storage | SQLite via GRDB.swift | Production-grade SQLite ORM |
| Encryption | iOS Keychain + CryptoKit | Device-bound key, hardware-backed |
| Web fetch | URLSession | Native, respects iOS ATS |
| Background tasks | BackgroundTasks framework | Survives screen lock |
| UI | SwiftUI | Native |

### Android

| Component | Technology | Why |
|---|---|---|
| Local LLM | llama.cpp via JNI or MLC-LLM | Runs on Snapdragon/Tensor chips |
| Governance kernel | Kotlin | Pure functions, straightforward translation |
| Storage | SQLite via Room | Google's official SQLite abstraction |
| Encryption | Android Keystore + Jetpack Security | Hardware-backed on modern devices |
| Web fetch | OkHttp | Standard |
| Background tasks | WorkManager | Persistent, survives restarts |
| UI | Jetpack Compose | Native |

### Cross-platform (one codebase)

| Component | Technology |
|---|---|
| Local LLM | MLC-LLM or Ollama (macOS arm64; iOS via WASM) |
| App | React Native or Flutter |
| Governance kernel | Pyodide (WASM) or native module |
| Storage | SQLite via expo-sqlite |

---

## Run lifecycle — example

```
SETUP (once)
  App installs. SandboxPolicy: base_knowledge_path only. Nothing else.
  User taps "+": grant read_folder("/Documents/contracts/")

DAY 1 — start procurement run
  create_run(task, sandbox_policy=policy, provider=LocalModelProvider(...))

  requirement_analyst
    reads /app/knowledge/     ← always allowed
    reads /Documents/contracts/ ← granted
    output: requirements + 6 gaps identified

  market_scout
    list_grants() → no web_read grants
    request_grant("web_read", "https://vendor-registry.example.com",
                  "need vendor pricing benchmarks")
    run → waiting_external_input

  [Phone notification: "market_scout wants to read vendor-registry.example.com"]
  [User taps: Allow]
  grant_approved → run resumes

  market_scout
    web_fetch("https://vendor-registry.example.com")
      DAR: WEB_READ + in grants → ALLOW
      returns vendor rows as vendor_proposal evidence (authority 0.70)
      PAAP scores them

  evaluator, recommender complete on-device (no network)

  recommender
    request_grant("web_write", "https://company.sharepoint.com/briefs/",
                  "share recommendation with procurement team")
    DAR: WEB_WRITE → ESCALATE → human gate

  [Phone: "Agent wants to send recommendation to SharePoint. Allow?"]
  [User approves]
    data sent, audit records: data left device 14:32,
    approved by user, destination SharePoint, grant_id g007

  run_completed
  Timeline: 09:00 started → 09:08 paused for grant → 09:09 resumed → 09:14 completed
```

---

## Key security properties

1. **Default deny.** Agent starts with zero permissions. Every access is explicit.
2. **Audit trail for every grant.** `policy_grant_added` / `policy_grant_revoked` in audit.jsonl.
3. **Data-out always escalates.** WEB_WRITE → ESCALATE, never auto-ALLOW.
4. **Model never leaves device.** LocalModelProvider has no network calls.
5. **One-time file grants.** `file_ingest` self-destructs after first use.
6. **Revocable.** Revoking a grant removes access from all future runs immediately.
7. **Policy is versioned.** `sandbox_policy_version` stored in run-record.json — reproducible.
8. **Cryptographic audit.** Every data-out event is an immutable record: timestamp, destination, user approval.

---

## What stays unchanged

- **DSC, PAAP, DAR logic** — unchanged; compile to Swift/Kotlin for mobile
- **Worker contracts** — unchanged; `read_paths` derived from SandboxPolicy instead of domain catalog
- **audit.jsonl** — unchanged; stored in SQLite on mobile
- **Evidence authority weights** — unchanged
- **Human gate** — the phone approval screen IS the human gate

---

## Implementation files

| File | Change |
|---|---|
| `shared/sandbox/policy.py` (new) | SandboxPolicy, SandboxGrant, grant management |
| `shared/sandbox/storage.py` (new) | load / save / add_grant / revoke_grant |
| `shared/providers/local.py` (new) | LocalModelProvider (llamacpp / MLX / MLC) |
| `shared/providers/registry.py` | `local/*` branch |
| `governance/dar.py` | WEB_READ, WEB_WRITE consequence classes |
| `modules/workers/tools.py` | web_fetch, list_grants, request_grant |
| `modules/runs/service.py` | create_run accepts sandbox_policy |
| `modules/contracts/generator.py` | override read_paths from sandbox |
| `server.py` | /api/sandbox/* endpoints |
