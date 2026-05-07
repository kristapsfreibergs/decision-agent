from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScopeContract:
    """Decision-scoped semantic context for a run.

    Defines what evidence types are allowed/required and which textual markers
    are forbidden in worker output. Persisted as data/runs/{run_id}/scope.json
    and embedded into every worker contract under "scope_contract" so the
    output validator can run pure (no run-record lookup mid-validation).
    """

    run_id: str
    domain: str
    allowed_evidence_classes: tuple[str, ...]
    required_evidence_classes: tuple[str, ...]
    out_of_scope_markers: tuple[str, ...]
    scope_phrase_blocklist: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "domain": self.domain,
            "allowed_evidence_classes": list(self.allowed_evidence_classes),
            "required_evidence_classes": list(self.required_evidence_classes),
            "out_of_scope_markers": list(self.out_of_scope_markers),
            "scope_phrase_blocklist": list(self.scope_phrase_blocklist),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScopeContract":
        return cls(
            run_id=value["run_id"],
            domain=value["domain"],
            allowed_evidence_classes=tuple(value.get("allowed_evidence_classes", ())),
            required_evidence_classes=tuple(value.get("required_evidence_classes", ())),
            out_of_scope_markers=tuple(value.get("out_of_scope_markers", ())),
            scope_phrase_blocklist=tuple(value.get("scope_phrase_blocklist", ())),
        )


def derive_scope_contract(
    run_id: str,
    domain: str,
    scope_profile: dict[str, Any] | None,
) -> ScopeContract:
    """Build a ScopeContract from a domain's SCOPE_PROFILE dict.

    A domain that omits SCOPE_PROFILE gets an empty (permissive) scope. DSC
    layer is only meaningful for domains that opt in by declaring the profile.
    """
    profile = scope_profile or {}
    return ScopeContract(
        run_id=run_id,
        domain=domain,
        allowed_evidence_classes=tuple(profile.get("allowed_evidence_classes", ())),
        required_evidence_classes=tuple(profile.get("required_evidence_classes", ())),
        out_of_scope_markers=tuple(profile.get("out_of_scope_markers", ())),
        scope_phrase_blocklist=tuple(profile.get("scope_phrase_blocklist", ())),
    )


def persist_scope_contract(scope: ScopeContract, runs_dir: Path) -> Path:
    target = runs_dir / scope.run_id / "scope.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(scope.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def load_scope_contract(run_id: str, runs_dir: Path) -> ScopeContract | None:
    target = runs_dir / run_id / "scope.json"
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return ScopeContract.from_dict(data)


def _iter_strings(value: Any):
    """Recursively yield every string contained in a JSON-like value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_strings(v)


def check_output_against_scope(
    output: dict[str, Any],
    scope: ScopeContract,
    *,
    enforce_required_evidence: bool = False,
) -> list[str]:
    """Return DSC violation messages for a worker output.

    Rules:
      1. No out_of_scope_marker literal substring may appear in any string field.
      2. No scope_phrase_blocklist phrase may appear (case-insensitive).
      3. Every declared evidence source's type must be in allowed_evidence_classes.
      4. If enforce_required_evidence is True, at least one source covering each
         required_evidence_class must be cited.
    """
    issues: list[str] = []

    if scope.out_of_scope_markers:
        for s in _iter_strings(output):
            lowered = s.lower()
            for marker in scope.out_of_scope_markers:
                if marker and marker.lower() in lowered:
                    issues.append(
                        f"dsc_scope: out-of-scope marker '{marker}' appeared in output."
                    )
                    break

    if scope.scope_phrase_blocklist:
        for s in _iter_strings(output):
            lowered = s.lower()
            for phrase in scope.scope_phrase_blocklist:
                if phrase and phrase.lower() in lowered:
                    issues.append(
                        f"dsc_scope: blocked phrase '{phrase}' appeared in output."
                    )
                    break

    sources = output.get("evidence_sources") or []
    cited_types: set[str] = set()
    if scope.allowed_evidence_classes:
        allowed = set(scope.allowed_evidence_classes)
        for source in sources:
            if isinstance(source, dict):
                src_type = str(source.get("type", "")).strip()
            elif isinstance(source, str):
                src_type = source.strip()
            else:
                continue
            if not src_type:
                continue
            cited_types.add(src_type)
            if src_type not in allowed:
                issues.append(
                    f"dsc_scope: evidence type '{src_type}' is not in allowed_evidence_classes."
                )

    if enforce_required_evidence and scope.required_evidence_classes:
        missing = [cls for cls in scope.required_evidence_classes if cls not in cited_types]
        if missing:
            issues.append(
                f"dsc_scope: required evidence classes missing from output: {sorted(missing)}."
            )

    return issues
