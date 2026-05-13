from __future__ import annotations

from typing import Any

from decision_agent.modules.architectures.domains.procurement_catalog import DEPENDENCIES, WORKER_CATALOG
from decision_agent.modules.architectures.domains.procurement_metadata import ACTION_GATE, CONSEQUENCE_TABLE, DOMAIN_ID, EVIDENCE_PROFILE, SCOPE_PROFILE

def build_procurement_decomposition(task: dict[str, Any], run_id: str) -> dict[str, Any]:
    task_title = task.get("title") or "Unnamed procurement"
    task_description = task.get("description") or ""
    task_context = f'Task: "{task_title}". {task_description}'.strip()

    packages = []
    for worker in WORKER_CATALOG:
        read_paths  = [p.replace("{run_id}", run_id) for p in worker["read_paths"]]
        write_paths = [p.replace("{run_id}", run_id) for p in worker["write_paths"]]
        output_fields = worker["output_fields"]
        scalar_fields = {
            "summary", "procurement_subject", "overall_risk_rating",
            "recommended_vendor", "ranking_reasoning", "decision_required",
        }
        goal = f"{task_context}\n\n{worker['goal_template']}"
        action_type = worker.get("dar_action_type")
        consequence_class = CONSEQUENCE_TABLE.get(action_type) if action_type else None
        max_steps = 20 if worker["phase"] in {"evaluate", "recommend"} else 10
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
            "allowed_tables": worker.get("allowed_tables", []),
            "validators": worker["validators"],
            "max_steps": max_steps,
            "dar_action_type": action_type,
            "dar_consequence_class": consequence_class,
            "output_schema": {
                "type": "object",
                "required": output_fields,
                "properties": {
                    f: {"type": "string" if f in scalar_fields else "array"}
                    for f in output_fields
                },
            },
            "completion_contract": f"Return {', '.join(output_fields)}.",
        })

    return {
        "domain": DOMAIN_ID,
        "task_subtype": "procurement",
        "affected_surfaces": [],
        "repo_context": {},
        "packages": packages,
        "dependencies": DEPENDENCIES,
        "human_questions": [],
        "evidence_profile": EVIDENCE_PROFILE,
        "scope_profile": SCOPE_PROFILE,
        "consequence_table": CONSEQUENCE_TABLE,
        "action_gate": ACTION_GATE,
        "package_outline": [
            {"id": p["id"], "work_layer": p["work_layer"], "phase_id": p["phase_id"]}
            for p in packages
        ],
        "worker_count_reasoning": {
            "total_workers": len(packages),
            "reason": (
                "requirement_analyst + market_scout + risk_assessor run in parallel during intake; "
                "evaluator scores and shortlists vendors using all three inputs; "
                "recommender produces a human-gated decision brief."
            ),
            "task_subtype": "procurement",
            "affected_surfaces": [],
        },
    }
