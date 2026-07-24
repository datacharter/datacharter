"""Aggregation pushdown for connector-extract sources (D12).

When a query is a pure single-connector-table aggregation, run the whole
GROUP BY on the remote (Snowflake) and return only the small result — instead
of extracting up to a million raw rows and aggregating locally. Deterministic,
no agent.

Only a dialect-safe whitelist is reconstructed (count/sum/avg/min/max, bare
group keys, fully-pushable WHERE, ORDER BY on outputs, LIMIT) — everything else
returns None and the caller falls back to the raw-extract path, which is always
correct. So a miss is a missed optimization, never a wrong answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from datacharter.engine.pushdown import _col_parts, _ident, _predicate_for, _walk

if TYPE_CHECKING:
    import duckdb

__all__ = ["RemoteAggregation", "build_remote_aggregation"]

_AGG = {"count_star", "count", "sum", "avg", "min", "max"}

# DuckDB defaults to NULLS LAST for both ASC and DESC; Snowflake's DESC default is
# NULLS FIRST. We always emit an explicit clause so the remote row order matches
# the local (non-pushed) result exactly.
_DEFAULT_NULLS = "NULLS LAST"
_EXPLICIT_NULLS = {"NULLS FIRST", "NULLS LAST"}


@dataclass
class RemoteAggregation:
    """A reconstructed single-table aggregation ready to run on the remote."""

    alias: str  # connector compat alias this targets
    columns: list[str]  # output column names, in order (for QueryResult)
    select_items: list[str]
    group_by: list[str]
    where: str | None = None
    order_by: str | None = None
    limit: int | None = None

    def render(self, remote_table: str) -> str:
        parts = [f"SELECT {', '.join(self.select_items)}", f"FROM {remote_table}"]
        if self.where:
            parts.append(f"WHERE {self.where}")
        if self.group_by:
            parts.append(f"GROUP BY {', '.join(self.group_by)}")
        if self.order_by:
            parts.append(f"ORDER BY {self.order_by}")
        if self.limit is not None:
            parts.append(f"LIMIT {self.limit}")
        return " ".join(parts)


def _select_item(entry: dict, group_cols: set[str]) -> tuple[str, str, bool] | None:
    """(sql, output_name, is_aggregate) for one select item, or None if not safe."""
    alias = entry.get("alias") or ""
    if alias and not _ident(alias):
        return None
    cls = entry.get("class")
    if cls == "COLUMN_REF":
        parts = _col_parts(entry)
        if not parts or not _ident(parts[1]) or parts[1].lower() not in group_cols:
            return None
        col = parts[1]
        return (f"{col} AS {alias}" if alias else col, alias or col, False)
    if cls == "FUNCTION":
        fn = (entry.get("function_name") or "").lower()
        if fn not in _AGG:
            return None
        kids = entry.get("children", [])
        if fn == "count_star":
            if kids:
                return None
            expr, default = "count(*)", "count_star()"
        else:
            if len(kids) != 1:
                return None
            parts = _col_parts(kids[0])
            if not parts or not _ident(parts[1]):
                return None
            distinct = "DISTINCT " if entry.get("distinct") else ""
            expr = f"{fn}({distinct}{parts[1]})"
            default = expr
        return (f"{expr} AS {alias}" if alias else expr, alias or default, True)
    return None


def _order_item(order: dict, columns: list[str], group_cols: set[str]) -> str | None:
    direction = "DESC" if order.get("type") == "DESCENDING" else "ASC"
    nulls = order.get("null_order")
    nulls = nulls if nulls in _EXPLICIT_NULLS else _DEFAULT_NULLS
    expr = order.get("expression") or {}
    if expr.get("class") == "COLUMN_REF":
        parts = _col_parts(expr)
        if not parts or not _ident(parts[1]):
            return None
        col = parts[1]
        if col not in columns and col.lower() not in group_cols:
            return None
        return f"{col} {direction} {nulls}"
    if expr.get("class") == "CONSTANT":  # ordinal, e.g. ORDER BY 2
        value = (expr.get("value") or {}).get("value")
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= len(columns):
            return f"{value} {direction} {nulls}"
    return None


def _modifiers(
    stmt: dict, columns: list[str], group_cols: set[str]
) -> tuple[str | None, int | None] | None:
    order_by: str | None = None
    limit: int | None = None
    for mod in stmt.get("modifiers", []):
        mtype = mod.get("type")
        if mtype == "ORDER_MODIFIER":
            frags = [_order_item(o, columns, group_cols) for o in mod.get("orders", [])]
            if any(f is None for f in frags):
                return None
            order_by = ", ".join(frags)
        elif mtype == "LIMIT_MODIFIER":
            if mod.get("offset"):
                return None
            value = ((mod.get("limit") or {}).get("value") or {}).get("value")
            if not isinstance(value, int) or isinstance(value, bool):
                return None
            limit = value
        else:
            return None  # DISTINCT / percent / unknown -> not safe to push
    return order_by, limit


def build_remote_aggregation(
    conn: duckdb.DuckDBPyConnection, sql: str, connector_aliases: set[str]
) -> RemoteAggregation | None:
    """Reconstruct a pushable single-table aggregation, or None if not safe."""
    connector_aliases = {t.lower() for t in connector_aliases}
    if not connector_aliases:
        return None
    try:
        stmt = json.loads(conn.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
        stmt = stmt["statements"][0]["node"]
    except Exception:
        return None
    if not isinstance(stmt, dict) or stmt.get("type") != "SELECT_NODE":
        return None
    if stmt.get("having") or stmt.get("qualify"):
        return None
    if (stmt.get("cte_map") or {}).get("map"):
        return None

    # FROM must be exactly one base table = a connector alias; no joins/subqueries.
    from_table = stmt.get("from_table") or {}
    tname = from_table.get("table_name")
    if not isinstance(tname, str) or tname.lower() not in connector_aliases:
        return None
    if from_table.get("left") or from_table.get("right"):
        return None
    base = [n for n in _walk(stmt) if isinstance(n, dict) and isinstance(n.get("table_name"), str)]
    selects = [n for n in _walk(stmt) if isinstance(n, dict) and n.get("type") == "SELECT_NODE"]
    if len(base) != 1 or len(selects) != 1:
        return None

    group_by: list[str] = []
    group_cols: set[str] = set()
    for g in stmt.get("group_expressions", []):
        parts = _col_parts(g) if isinstance(g, dict) else None
        if not parts or not _ident(parts[1]):
            return None
        group_by.append(parts[1])
        group_cols.add(parts[1].lower())

    # Only a plain GROUP BY (the full column set); reject ROLLUP/CUBE/GROUPING SETS.
    if (stmt.get("group_sets") or []) not in ([], [[]], [list(range(len(group_by)))]):
        return None

    select_items: list[str] = []
    columns: list[str] = []
    has_agg = False
    for entry in stmt.get("select_list", []):
        item = _select_item(entry, group_cols) if isinstance(entry, dict) else None
        if item is None:
            return None
        select_items.append(item[0])
        columns.append(item[1])
        has_agg = has_agg or item[2]
    if not has_agg:
        return None  # not an aggregation — the normal path handles it fine

    where = stmt.get("where_clause")
    where_sql: str | None = None
    if where:
        conjuncts = where["children"] if where.get("type") == "CONJUNCTION_AND" else [where]
        frags = [_predicate_for(c) if isinstance(c, dict) else None for c in conjuncts]
        if any(f is None for f in frags):
            return None  # can't fully represent the filter remotely -> unsafe
        where_sql = " AND ".join(f[1] for f in frags)

    mods = _modifiers(stmt, columns, group_cols)
    if mods is None:
        return None
    order_by, limit = mods

    return RemoteAggregation(
        alias=tname.lower(),
        columns=columns,
        select_items=select_items,
        group_by=group_by,
        where=where_sql,
        order_by=order_by,
        limit=limit,
    )
