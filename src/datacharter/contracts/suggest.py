"""Self-writing guides: mine query history for the habits humans repeat.

DuckDB's own `json_serialize_sql` parses each recorded query; recurring WHERE
predicates and relation co-occurrences become guide suggestions with evidence
("14 of 20 recent queries on `sales` filter `refunded = false`"). Deterministic
and offline — no model involved.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

__all__ = ["Suggestion", "mine_history", "render_suggestions", "apply_suggestions"]

_OPS = {
    "COMPARE_EQUAL": "=",
    "COMPARE_NOTEQUAL": "!=",
    "COMPARE_LESSTHAN": "<",
    "COMPARE_GREATERTHAN": ">",
    "COMPARE_LESSTHANOREQUALTO": "<=",
    "COMPARE_GREATERTHANOREQUALTO": ">=",
}


@dataclass
class Suggestion:
    kind: str  # "filter" | "join"
    relation: str
    text: str
    count: int
    total: int


def _parse_where(sql: str) -> dict | None:
    import duckdb

    try:
        raw = duckdb.sql("SELECT json_serialize_sql(?)", params=[sql]).fetchone()[0]
        ast = json.loads(raw)
        if ast.get("error"):
            return None
        return ast["statements"][0]["node"].get("where_clause")
    except Exception:
        return None


def _conjuncts(node: dict) -> list[dict]:
    if node.get("type") == "CONJUNCTION_AND":
        out: list[dict] = []
        for c in node.get("children", []):
            out.extend(_conjuncts(c))
        return out
    return [node]


def _render_side(node: dict) -> tuple[str, str] | None:
    """(kind, text) where kind is 'col' or 'const'; None when unrenderable."""
    t = node.get("type")
    if t == "COLUMN_REF":
        names = node.get("column_names") or []
        return ("col", names[-1]) if names else None
    if t == "OPERATOR_CAST":
        child = _render_side(node.get("child") or {})
        if child and child[0] == "const" and node.get("cast_type", {}).get("id") == "BOOLEAN":
            return ("const", {"f": "false", "t": "true"}.get(child[1].strip("'"), child[1]))
        return child
    if t == "VALUE_CONSTANT":
        val = node.get("value", {})
        if val.get("is_null"):
            return ("const", "NULL")
        type_id = (val.get("type") or {}).get("id", "")
        raw = str(val.get("value"))
        if type_id in ("VARCHAR",):
            return ("const", f"'{raw}'")
        return ("const", raw)
    return None


def _render_predicate(node: dict) -> str | None:
    op = _OPS.get(node.get("type", ""))
    if op is None:
        return None
    left = _render_side(node.get("left") or {})
    right = _render_side(node.get("right") or {})
    if not left or not right:
        return None
    if left[0] == "col" and right[0] == "const":
        return f"{left[1]} {op} {right[1]}"
    if left[0] == "const" and right[0] == "col":
        flipped = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}.get(op, op)
        return f"{right[1]} {flipped} {left[1]}"
    return None


def mine_history(
    workspace: Path | str, min_count: int = 3, min_share: float = 0.4
) -> list[Suggestion]:
    from datacharter.contracts.guides import load_guides
    from datacharter.engine.history import read_history

    entries = read_history(Path(workspace), limit=500)
    per_rel_total: Counter = Counter()
    per_rel_pred: dict[str, Counter] = defaultdict(Counter)
    pair_counts: Counter = Counter()

    for e in entries:
        relations = sorted({str(r) for r in (e.get("relations") or [])})
        for pair in combinations(relations, 2):
            pair_counts[pair] += 1
        preds: set[str] = set()
        where = _parse_where(e.get("sql") or "")
        if where is not None:
            for c in _conjuncts(where):
                p = _render_predicate(c)
                if p:
                    preds.add(p)
        for rel in relations:
            per_rel_total[rel] += 1
            for p in preds:
                per_rel_pred[rel][p] += 1

    existing = load_guides(workspace).lower()
    suggested_file = Path(workspace) / "guides" / "suggested.md"
    if suggested_file.exists():
        existing += suggested_file.read_text().lower()

    out: list[Suggestion] = []
    for rel, preds_counter in per_rel_pred.items():
        total = per_rel_total[rel]
        for pred, count in preds_counter.most_common():
            if count >= min_count and count / total >= min_share:
                if pred.lower() in existing:
                    continue
                out.append(Suggestion(
                    kind="filter", relation=rel, count=count, total=total,
                    text=(
                        f"Queries on `{rel}` usually filter `{pred}` "
                        f"({count} of {total} recent queries) — treat it as the default filter."
                    ),
                ))
    for (a, b), count in pair_counts.most_common():
        if count >= min_count:
            line = f"`{a}` and `{b}` are usually queried together — they join naturally."
            if line.lower() in existing:
                continue
            out.append(Suggestion(
                kind="join", relation=f"{a}+{b}", count=count,
                total=len(entries), text=line,
            ))
    return out


def render_suggestions(suggestions: list[Suggestion]) -> str:
    if not suggestions:
        return "No new suggestions — your guides already cover your query habits."
    lines = ["Guide suggestions mined from your query history:\n"]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"  {i}. [{s.kind}] {s.text}")
    return "\n".join(lines)


def apply_suggestions(workspace: Path | str, suggestions: list[Suggestion]) -> Path:
    """Append the batch to guides/suggested.md under a dated heading."""
    import datetime as _dt

    gdir = Path(workspace) / "guides"
    gdir.mkdir(exist_ok=True)
    path = gdir / "suggested.md"
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")
    block = [f"\n## Suggested from query history ({stamp})\n"]
    block += [f"- {s.text}" for s in suggestions]
    existing = path.read_text() if path.exists() else "# Suggested guides\n"
    path.write_text(existing + "\n".join(block) + "\n")
    return path
