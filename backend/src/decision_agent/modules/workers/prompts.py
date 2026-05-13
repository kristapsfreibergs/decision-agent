from __future__ import annotations

import json
from typing import Any

from decision_agent.modules.governance.layer_config import LayerConfig

MAX_CONTEXT_CHARS_PER_FILE = 4_000

def _build_system_prompt(contract: dict[str, Any]) -> str:
    output_schema = json.dumps(contract.get("output_schema", {}), indent=2)
    validators = ", ".join(contract.get("validators", []))
    cfg = LayerConfig.from_dict(contract.get("layer_config"))

    paap_block = ""
    if cfg.paap_enabled and "evidence_sources_declared" in (contract.get("validators") or []):
        evidence_profile = contract.get("evidence_profile") or {}
        weights = evidence_profile.get("authority_weights") or {}
        allowed = sorted(t for t, w in weights.items() if float(w) > 0.0)
        paap_block = (
            "\n\nEVIDENCE CITATION RULES (PAAP):\n"
            "- The evidence_sources field must be a JSON array of objects.\n"
            "- Each object has: id (string), type (string), excerpt (short string, ≤15 words), "
            "created_at (ISO date string, e.g. '2024-01-01' — use the document date if known, "
            "or today's date if the source is current; null only if truly unknown).\n"
            f"- type must be one of: {', '.join(allowed) if allowed else '<see contract>'}\n"
            "- Do NOT cite model_inference. Do NOT make up sources.\n"
            "- Every claim in your output must be traceable to one of the evidence_sources entries.\n"
        )

    scope_block = ""
    if cfg.dsc_enabled and contract.get("scope_contract"):
        scope = contract["scope_contract"]
        markers = scope.get("out_of_scope_markers", [])
        phrases = scope.get("scope_phrase_blocklist", [])
        required_classes = scope.get("required_evidence_classes", [])
        required_line = (
            f"- You MUST cite at least one source of each required type: {', '.join(required_classes)}\n"
            if required_classes else ""
        )
        scope_block = (
            "\n\nSCOPE RULES (DSC):\n"
            f"- Out-of-scope markers (must NOT appear in output): {', '.join(markers) or 'none'}\n"
            f"- Forbidden phrases (must NOT appear, case-insensitive): {', '.join(phrases) or 'none'}\n"
            f"{required_line}"
            "- Stay strictly inside the decision scope. State 'unknown' rather than speculating.\n"
        )

    return f"""You are a bounded worker agent operating under a strict contract.

Worker ID: {contract["worker_id"]}
Layer: {contract.get("work_layer", contract.get("layer", ""))}
Goal: {contract["goal"]}

Constraints:
- You may only read from: {", ".join(contract.get("read_paths", []))}
- You may only write to: {", ".join(contract.get("write_paths", []))}
- Allowed tools: {", ".join(contract.get("allowed_tools", []))}
- Validators that will check your output: {validators}
- Max steps: {contract.get("max_steps", 5)}
- Completion contract: {contract.get("completion_contract", "")}

MANDATORY TOOL USE:
- You MUST call your tools to do real work. Do NOT fabricate results.
- If your goal involves reading files: call read_file or list_files FIRST.
- If your goal involves writing or creating files: call write_file to actually write them.
- If write_file is available in your tools, you MUST call write_file before your final JSON.
- Do NOT claim files_changed unless you called write_file and it returned "OK:".
- Do NOT summarise what you "would" do — actually do it with tools.
- Produce the final JSON ONLY after your tool calls are complete.

OUTPUT RULES (strictly enforced):
- Your ENTIRE final response must be ONE valid JSON object.
- Start your response with {{ and end with }}.
- No preamble, no explanation, no markdown, no code fences.
- Keep all string values SHORT. Summaries ≤ 2 sentences. Lists use brief labels, not prose paragraphs. No repetition of information already in other fields.
- Schema you must match:
{output_schema}{paap_block}{scope_block}"""


def _build_user_prompt(contract: dict[str, Any], context_files: dict[str, str]) -> str:
    task_ctx = contract.get("context", {})
    lines = [
        f"Task: {task_ctx.get('task_title', 'Unnamed task')}",
        f"Description: {task_ctx.get('task_summary', '')}",
        f"Router reason: {task_ctx.get('router_reason', '')}",
        "",
        "Start by calling list_files or read_file to explore the codebase. Then call write_file to make changes. Only return the final JSON after your tool calls are done.",
    ]
    if context_files:
        lines.append("\nAvailable context files:")
        for path, content in context_files.items():
            lines.append(f"\n--- {path} ---\n{content[:MAX_CONTEXT_CHARS_PER_FILE]}")
    return "\n".join(lines)
