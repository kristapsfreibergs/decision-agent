from __future__ import annotations

import os
from pathlib import Path

from decision_agent.shared.memory.base import MemoryProvider


def get_memory_provider(data_root: Path | None = None) -> MemoryProvider:
    """Return the configured memory provider.

    MEMORY_PROVIDER env var selects the implementation:
      filesystem (default) — keyword search, no dependencies
      vector               — semantic search via sentence-transformers + FAISS
                             (requires: pip install sentence-transformers faiss-cpu)
    """
    root = data_root or Path.cwd() / "data"
    name = os.environ.get("MEMORY_PROVIDER", "filesystem").strip().lower()

    if name == "vector":
        try:
            from decision_agent.shared.memory.vector import VectorMemoryProvider
            return VectorMemoryProvider(root)
        except ImportError:
            pass  # Fall back to filesystem if deps missing

    from decision_agent.shared.memory.filesystem import FilesystemMemoryProvider
    return FilesystemMemoryProvider(root)
