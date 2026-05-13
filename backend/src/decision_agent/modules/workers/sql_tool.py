from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

AuditEmit = Callable[..., None]

_SCHEMA_MAP_CACHE: dict[str, Any] | None = None


def _load_schema_map(project_root: Path) -> dict[str, Any]:
    global _SCHEMA_MAP_CACHE
    if _SCHEMA_MAP_CACHE is not None:
        return _SCHEMA_MAP_CACHE
    path = project_root / "configs" / "data-sources" / "schema-map.json"
    if not path.exists():
        return {}
    try:
        _SCHEMA_MAP_CACHE = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _SCHEMA_MAP_CACHE = {}
    return _SCHEMA_MAP_CACHE


def _execute_query_sql(
    params: dict[str, Any],
    contract: dict[str, Any],
    project_root: Path,
    audit_emit: AuditEmit,
) -> str:
    table = str(params.get("table", "")).strip()
    filters: dict[str, Any] = params.get("filters") or {}
    limit = min(int(params.get("limit") or 20), 20)

    allowed_tables: list[str] = contract.get("allowed_tables") or []
    if allowed_tables and table not in allowed_tables:
        audit_emit("tool_called", tool="query_sql", table=table, blocked=True,
                   reason="not in allowed_tables")
        return f"ERROR: table '{table}' is not in the contract's allowed_tables: {allowed_tables}"

    schema_map = _load_schema_map(project_root)
    tables = schema_map.get("tables", {})
    if table not in tables:
        audit_emit("tool_called", tool="query_sql", table=table, blocked=True,
                   reason="not in schema-map")
        return (
            f"ERROR: table '{table}' is not in schema-map.json. "
            f"Available tables: {sorted(tables.keys())}"
        )

    table_def = tables[table]
    conn_name = table_def["connection"]
    connections = schema_map.get("connections", {})
    conn_def = connections.get(conn_name, {})

    evidence_class = table_def["evidence_class"]
    timestamp_col = table_def.get("timestamp_col")
    excerpt_cols: list[str] = table_def.get("excerpt_cols", [])
    pk_col: str = table_def.get("pk_col", "rowid")

    where_parts: list[str] = []
    where_values: list[Any] = []
    for col, val in filters.items():
        if col and all(c.isalnum() or c == "_" for c in col):
            where_parts.append(f'"{col}" = ?')
            where_values.append(val)

    sql = f'SELECT * FROM "{table}"'
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += f" LIMIT {limit}"

    try:
        if conn_def.get("type") == "sqlite":
            db_path = project_root / conn_def.get("path", "archive/data/demo.db")
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, where_values).fetchall()
            conn.close()
        else:
            return f"ERROR: connection type '{conn_def.get('type')}' not yet supported."
    except (sqlite3.Error, OSError) as exc:
        audit_emit("tool_called", tool="query_sql", table=table, error=str(exc)[:200])
        return f"ERROR: query failed: {exc}"

    evidence_sources = []
    for row in rows:
        row_dict = dict(row)
        pk_value = row_dict.get(pk_col, "unknown")
        excerpt_parts = [
            f"{col}={row_dict[col]}"
            for col in excerpt_cols
            if col in row_dict and row_dict[col] is not None
        ]
        evidence_sources.append({
            "id": f"{table}#{pk_value}",
            "type": evidence_class,
            "excerpt": "; ".join(excerpt_parts),
            "created_at": str(row_dict.get(timestamp_col, "")) if timestamp_col else None,
            "_row": row_dict,
        })

    audit_emit("tool_called", tool="query_sql", table=table,
               rows=len(evidence_sources), evidence_class=evidence_class)
    return json.dumps(evidence_sources, indent=2, ensure_ascii=False, default=str)
