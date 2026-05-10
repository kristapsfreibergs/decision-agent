from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.shared.memory.base import MemoryHit, MemoryItem, MemoryProvider


class FilesystemMemoryProvider(MemoryProvider):
    """Keyword-based memory backed by JSONL files in data/memory/{domain}/.

    Fast, no dependencies, no embedding model. Keyword matching only —
    suitable for V1 and thesis demos. Swap for VectorMemoryProvider when
    semantic search quality matters.

    Layout:
        data/memory/{domain}/{run_id}_{worker_id}.jsonl
    Each line is one MemoryItem serialised as JSON.
    """

    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "memory"

    def _domain_dir(self, domain: str) -> Path:
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", domain)
        return self._root / slug

    def write(self, item: MemoryItem) -> str:
        memory_id = f"mem_{uuid4().hex[:12]}"
        domain_dir = self._domain_dir(item.domain)
        domain_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{item.source_run_id}_{item.worker_id}.jsonl"
        entry = {
            "memory_id": memory_id,
            "source_run_id": item.source_run_id,
            "worker_id": item.worker_id,
            "evidence_class": item.evidence_class,
            "content": item.content,
            "created_at": item.created_at,
            "domain": item.domain,
            "authority_score": item.authority_score,
            **(item.extra or {}),
        }
        with (domain_dir / filename).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return memory_id

    def search(
        self,
        query: str,
        scope: dict[str, Any],
        limit: int = 10,
    ) -> list[MemoryHit]:
        domain = scope.get("domain", "")
        allowed_classes = set(scope.get("allowed_evidence_classes") or [])
        domain_dir = self._domain_dir(domain)
        if not domain_dir.exists():
            return []

        query_tokens = {t.lower() for t in re.split(r"\W+", query) if len(t) > 2}
        scored: list[tuple[float, dict[str, Any]]] = []

        for jsonl_file in sorted(domain_dir.glob("*.jsonl")):
            try:
                lines = jsonl_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # DSC enforcement: only return allowed evidence classes
                if allowed_classes and entry.get("evidence_class") not in allowed_classes:
                    continue
                content = entry.get("content", "").lower()
                hit_count = sum(1 for t in query_tokens if t in content)
                if hit_count == 0:
                    continue
                relevance = hit_count / max(len(query_tokens), 1)
                scored.append((relevance, entry))

        scored.sort(key=lambda x: -x[0])
        return [
            MemoryHit(
                memory_id=e.get("memory_id", ""),
                source_run_id=e.get("source_run_id", ""),
                worker_id=e.get("worker_id", ""),
                evidence_class=e.get("evidence_class", ""),
                excerpt=e.get("content", "")[:300],
                authority_score=float(e.get("authority_score", 0.0)),
                created_at=e.get("created_at", ""),
                relevance_score=round(rel, 4),
            )
            for rel, e in scored[:limit]
        ]

    def count(self, domain: str) -> int:
        domain_dir = self._domain_dir(domain)
        if not domain_dir.exists():
            return 0
        total = 0
        for jsonl_file in domain_dir.glob("*.jsonl"):
            try:
                total += sum(1 for line in jsonl_file.read_text("utf-8").splitlines() if line.strip())
            except OSError:
                pass
        return total
