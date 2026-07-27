"""Local query history + lineage aggregation."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

__all__ = ["record", "read_history", "lineage"]

_MAX = 500


def _path(workspace: Path) -> Path:
    return Path(workspace) / ".datacharter" / "history.jsonl"


def record(workspace: Path, sql: str, row_count: int, provenance: dict | None) -> None:
    """Append one run to history, trimming to the most recent _MAX entries."""
    p = _path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    prov = provenance or {}
    entry = {
        "ts": _dt.datetime.now(_dt.UTC).isoformat(),
        "sql": sql,
        "row_count": row_count,
        "relations": prov.get("relations", []),
        "columns": prov.get("columns", []),
        "lineage": prov.get("lineage", {}),
    }
    lines = p.read_text().splitlines() if p.exists() else []
    lines.append(json.dumps(entry, default=str))
    p.write_text("\n".join(lines[-_MAX:]) + "\n")


def read_history(workspace: Path, limit: int = 50) -> list[dict]:
    """Recent runs, newest first, up to `limit`."""
    p = _path(workspace)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out[: max(0, limit)]


def lineage(workspace: Path) -> dict:
    """Fold provenance across history into a co-read + column-lineage graph."""
    rels: dict[str, dict] = {}
    cols: dict[str, list[str]] = {}
    for e in read_history(workspace, limit=_MAX):
        related = list(dict.fromkeys(e.get("relations") or []))
        for r in related:
            node = rels.setdefault(r, {"co_read": {}})
            for other in related:
                if other != r:
                    node["co_read"][other] = node["co_read"].get(other, 0) + 1
        for out_col, inputs in (e.get("lineage") or {}).items():
            merged = dict.fromkeys(cols.get(out_col, []))
            for i in inputs:
                merged[i] = None
            cols[out_col] = list(merged)
    return {"relations": rels, "columns": cols}
