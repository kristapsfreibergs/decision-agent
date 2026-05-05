from __future__ import annotations

from typing import Any


def build_topology(goal_structure: dict[str, Any]) -> dict[str, Any]:
    shape = goal_structure["shape"]
    modifiers = set(goal_structure.get("modifiers", []))

    if shape == "search":
        phases = [
            _phase("frame", "frame_search", "Frame the search space and constraints.", False),
            _phase("explore", "explore_candidates", "Explore candidate options and evidence.", True),
            _phase("converge", "converge_result", "Converge on a justified result.", False),
        ]
        completion = "done means convergence on a justified best candidate"
        dependency_model = "explore can fan out; converge waits on explored candidates"
    elif shape == "funnel":
        phases = [
            _phase("collect", "collect_candidates", "Collect candidate options.", True),
            _phase("narrow", "narrow_set", "Narrow options against criteria.", True),
            _phase("decide", "select_result", "Select the recommended outcome.", False),
        ]
        completion = "done means a narrowed recommendation is selected"
        dependency_model = "narrow depends on collected candidates; decide waits on narrowed set"
    elif shape == "debate":
        phases = [
            _phase("position_a", "argue_primary", "Develop the primary position.", True),
            _phase("position_b", "argue_counter", "Develop the counter-position.", True),
            _phase("adjudicate", "adjudicate_positions", "Resolve competing claims.", False),
        ]
        completion = "done means adjudication resolves competing positions"
        dependency_model = "argument phases run in parallel; adjudication waits on both"
    elif shape == "checker":
        phases = [
            _phase("collect", "collect_evidence", "Collect required evidence and artifacts.", True),
            _phase("verify", "verify_claims", "Verify claims against evidence.", False),
            _phase("gate", "approve_or_reject", "Apply the final review gate.", False),
        ]
        completion = "done means verification completes and the gate resolves"
        dependency_model = "verify waits on evidence collection; gate waits on verification"
    else:
        phases = [
            _phase("scope", "scope_artifact", "Scope the artifact and constraints.", False),
            _phase("assemble", "assemble_artifact", "Assemble the requested artifact.", True),
            _phase("review", "review_artifact", "Review the assembled result.", False),
        ]
        completion = "done means a complete artifact has been assembled and reviewed"
        dependency_model = "assembly depends on scoped intent; review waits on assembled artifact"

    gates = []
    if "human_gate_required" in modifiers or "high_risk" in modifiers:
        gates.append(
            {
                "id": "human_gate",
                "placement": phases[-1]["id"],
                "rule": "Human approval is required before consequential execution continues.",
            }
        )

    return {
        "shape": shape,
        "phases": phases,
        "dependency_model": dependency_model,
        "completion_semantics": completion,
        "gates": gates,
        "topology_reasoning": f"{shape} topology selected from goal structure; phases derived from execution shape, not domain labels.",
    }


def _phase(phase_id: str, slot: str, done_means: str, parallelizable: bool) -> dict[str, Any]:
    return {
        "id": phase_id,
        "slot": slot,
        "parallelizable": parallelizable,
        "done_means": done_means,
    }
