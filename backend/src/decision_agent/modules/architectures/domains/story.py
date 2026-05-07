from __future__ import annotations

from typing import Any

# Story domain worker catalog.
# Shape: tree — briefer + researcher run in parallel, writer merges both, then sequential refine → style.

DOMAIN_ID = "story"

# Keywords used by the domain detector in proposal.py for provider-less fallback.
DETECTION_KEYWORDS = ("story", "tale", "narrative", "fiction", "novel", "fable", "write a")

DOMAIN_SPEC = {
    "goal_structure": {
        "shape": "tree",
        "modifiers": [],
        "reasoning": "Story tasks use a parallel intake (brief + research) feeding a sequential draft → refine → style pipeline.",
    },
    "topology": {
        "shape": "tree",
        "phases": [
            {"id": "intake", "slot": "parallel_intake", "parallelizable": True,  "done_means": "Brief and research complete."},
            {"id": "draft",  "slot": "write_draft",     "parallelizable": False, "done_means": "Complete story draft written."},
            {"id": "refine", "slot": "proofread",        "parallelizable": False, "done_means": "Draft proofread and corrected."},
            {"id": "style",  "slot": "apply_voice",      "parallelizable": False, "done_means": "Final story in human's voice written."},
        ],
        "dependency_model": "briefer + researcher parallel in intake; writer waits on both; proofreader and stylist sequential",
        "completion_semantics": "done means final.md is produced",
        "gates": [],
        "topology_reasoning": "Story domain: parallel intake branches merge into sequential draft → refine → style.",
    },
}

WORKER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "briefer",
        "phase": "intake",
        "parallelizable": True,
        "role": "briefer",
        "goal_template": "Extract story intent from the task. Define: genre, target audience, approximate length, key characters, setting, mood, and any specific elements the human wants included. Fill gaps with sensible defaults — do not block unless the task is completely empty. Check knowledge/story/ for past preferences.",
        "read_paths": ["knowledge/story/**"],
        "write_paths": ["data/runs/{run_id}/workspace/brief.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_fields": ["summary", "genre", "audience", "length", "characters", "mood", "elements"],
    },
    {
        "id": "researcher",
        "phase": "intake",
        "parallelizable": True,
        "role": "researcher",
        "goal_template": "Research the current market for this story type. Find: what is selling well in the target market right now, genre conventions and reader expectations, cultural traditions and sensitivities for the target audience. Use web search if available, fall back to knowledge/markets/ if not.",
        "read_paths": ["knowledge/markets/**"],
        "write_paths": ["data/runs/{run_id}/workspace/research.md"],
        "allowed_tools": ["read_file", "write_file", "list_files", "web_search"],
        "validators": ["write_scope"],
        "output_fields": ["summary", "market_trends", "genre_conventions", "cultural_notes"],
    },
    {
        "id": "writer",
        "phase": "draft",
        "parallelizable": False,
        "role": "writer",
        "goal_template": "Write a complete story draft using the brief and market research. The story must have a clear beginning, middle, and end. Follow the genre, tone, characters, and elements defined in the brief. Apply market insights from research to make it resonate with the target audience.",
        "read_paths": ["data/runs/{run_id}/workspace/brief.md", "data/runs/{run_id}/workspace/research.md"],
        "write_paths": ["data/runs/{run_id}/workspace/draft.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_fields": ["summary", "word_count", "draft_path"],
    },
    {
        "id": "proofreader",
        "phase": "refine",
        "parallelizable": False,
        "role": "proofreader",
        "goal_template": "Review the story draft for grammar, spelling, punctuation, sentence flow, pacing, and narrative consistency. Check character names are consistent, plot has no gaps, and the ending resolves the story. Produce a corrected version.",
        "read_paths": ["data/runs/{run_id}/workspace/draft.md"],
        "write_paths": ["data/runs/{run_id}/workspace/proofread.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_fields": ["summary", "issues_found", "proofread_path"],
    },
    {
        "id": "stylist",
        "phase": "style",
        "parallelizable": False,
        "role": "stylist",
        "goal_template": "Apply the human's personal writing voice and style to the proofread story. Read their past writing samples from knowledge/voice/ to understand their style patterns (sentence length, vocabulary, rhythm, tone). If no samples exist, ask what style they prefer before proceeding. Produce the final polished story.",
        "read_paths": [
            "data/runs/{run_id}/workspace/proofread.md",
            "data/runs/{run_id}/workspace/brief.md",
            "knowledge/voice/**",
        ],
        "write_paths": ["data/runs/{run_id}/workspace/final.md"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_fields": ["summary", "style_notes", "final_path"],
    },
]

DEPENDENCIES = [
    {"from": "writer",      "on": "briefer",     "reason": "Writer needs the brief before drafting."},
    {"from": "writer",      "on": "researcher",  "reason": "Writer needs market research before drafting."},
    {"from": "proofreader", "on": "writer",      "reason": "Proofreader works on the draft."},
    {"from": "stylist",     "on": "proofreader", "reason": "Stylist works on the proofread version."},
]

PHASES = [
    {"id": "intake",  "done_means": "Brief and research complete.",          "parallelizable": True},
    {"id": "draft",   "done_means": "Complete story draft written.",         "parallelizable": False},
    {"id": "refine",  "done_means": "Draft proofread and corrected.",        "parallelizable": False},
    {"id": "style",   "done_means": "Final story in human's voice written.", "parallelizable": False},
]


def build_story_decomposition(task: dict[str, Any], run_id: str) -> dict[str, Any]:
    task_title = task.get("title") or "Unnamed story"
    task_description = task.get("description") or ""
    task_context = f'Task: "{task_title}". {task_description}'.strip()

    packages = []
    for worker in WORKER_CATALOG:
        read_paths = [p.replace("{run_id}", run_id) for p in worker["read_paths"]]
        write_paths = [p.replace("{run_id}", run_id) for p in worker["write_paths"]]
        output_fields = worker["output_fields"]
        scalar_fields = {"summary", "draft_path", "proofread_path", "final_path", "word_count"}
        goal = f"{task_context}\n\n{worker['goal_template']}"
        packages.append({
            "id": worker["id"],
            "worker_id": worker["id"],
            "phase_id": worker["phase"],
            "worker_role": worker["role"],
            "work_layer": worker["phase"],
            "goal": goal,
            "read_paths": read_paths,
            "write_paths": write_paths,
            "allowed_tools": worker["allowed_tools"],
            "validators": worker["validators"],
            "output_schema": {
                "type": "object",
                "required": output_fields,
                "properties": {f: {"type": "string" if f in scalar_fields else "array"} for f in output_fields},
            },
            "completion_contract": f"Return {', '.join(output_fields)}.",
        })

    return {
        "domain": DOMAIN_ID,
        "task_subtype": "story",
        "affected_surfaces": [],
        "repo_context": {},
        "packages": packages,
        "dependencies": DEPENDENCIES,
        "human_questions": [],
        "package_outline": [{"id": p["id"], "work_layer": p["work_layer"], "phase_id": p["phase_id"]} for p in packages],
        "worker_count_reasoning": {
            "total_workers": len(packages),
            "reason": "briefer + researcher run in parallel, writer merges both, proofreader refines, stylist applies voice.",
            "task_subtype": "story",
            "affected_surfaces": [],
        },
    }
