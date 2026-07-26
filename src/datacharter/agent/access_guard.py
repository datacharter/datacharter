"""Agent-surface access guard: a masked column may be SELECTed (value masked
downstream) but never used to filter, join, group, or order the result.

Reuses DuckDB's parse tree (`json_serialize_sql`, the same tree the read-only
guard and provenance walk). Only column references directly in the top-level
SELECT projection list are permitted to touch a masked column; a masked
reference anywhere else — WHERE/JOIN/GROUP/ORDER/HAVING/window, or inside any
subquery/CTE/set-operation — is refused, fail-closed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

import duckdb

__all__ = ["AgentAccessDenied", "check_query_access"]

# Node types that open a nested query scope: refs beneath them are never the
# top-level projection, so a masked ref there is a violation.
_QUERY_NODE_TYPES = frozenset({"SELECT_NODE", "SET_OPERATION_NODE", "SUBQUERY"})


class AgentAccessDenied(Exception):
    """A governed query references a masked column outside the SELECT list."""


def check_query_access(
    sql: str,
    *,
    is_masked: Callable[[str, str, str], bool],
    masked_names: set[str],
) -> None:
    tree = _parse(sql)
    if tree is None:
        _failclosed_token_scan(sql, masked_names)
        return
    node = _top_select_node(tree)
    alias_map, relations = _collect_tables(tree)

    violations: set[str] = set()

    def masked_ref(names: list[str]) -> str | None:
        """Return the column name if this ref resolves to a masked column, else None."""
        col = names[-1]
        qualifier = names[-2] if len(names) >= 2 else None
        if qualifier and qualifier in alias_map:
            src, tbl = _split(alias_map[qualifier])
            return col if is_masked(src, tbl, col) else None
        # bare name, or a qualifier we can't resolve to an alias: fail-closed by
        # checking every touched relation (masked in any -> treat as masked).
        for q in relations:
            src, tbl = _split(q)
            if is_masked(src, tbl, col):
                return col
        return None

    def walk(n: object, allowed: bool) -> None:
        if isinstance(n, dict):
            t = n.get("type")
            if isinstance(t, str):  # some nodes carry a dict `type` (logical-type descriptors)
                if t == "COLUMN_REF":
                    names = n.get("column_names")
                    if isinstance(names, list) and names and not allowed:
                        hit = masked_ref(names)
                        if hit:
                            violations.add(hit)
                    return
                if t in _QUERY_NODE_TYPES:
                    allowed = False  # inside a nested query, nothing is top-level projection
            for value in n.values():
                walk(value, allowed)
        elif isinstance(n, list):
            for item in n:
                walk(item, allowed)

    if isinstance(node, dict) and node.get("type") == "SELECT_NODE":
        for key, value in node.items():
            walk(value, allowed=(key == "select_list"))
    else:
        walk(node, allowed=False)  # set-op / unusual top node: nothing is allowed

    if violations:
        cols = ", ".join(sorted(violations))
        raise AgentAccessDenied(
            f"Access denied: column(s) {cols} are masked; they can be selected "
            f"(values return as '•••') but not used in WHERE, JOIN, "
            f"GROUP BY, ORDER BY, or a subquery."
        )


def _failclosed_token_scan(sql: str, masked_names: set[str]) -> None:
    low = sql.lower()
    for name in masked_names:
        if re.search(rf"\b{re.escape(name.lower())}\b", low):
            raise AgentAccessDenied(
                f"Access denied: could not verify access safety and the query "
                f"references a masked column ('{name}')."
            )


def _top_select_node(tree: dict) -> object:
    stmts = tree.get("statements") if isinstance(tree, dict) else None
    return stmts[0].get("node") if stmts else None


def _collect_tables(tree: object) -> tuple[dict[str, str], list[str]]:
    alias_map: dict[str, str] = {}
    relations: set[str] = set()

    def walk(n: object) -> None:
        if isinstance(n, dict):
            if n.get("type") == "BASE_TABLE":
                qualified = ".".join(
                    p
                    for p in (n.get("catalog_name"), n.get("schema_name"), n.get("table_name"))
                    if p
                )
                if qualified:
                    relations.add(qualified)
                    alias = n.get("alias") or n.get("table_name")
                    if alias:
                        alias_map[alias] = qualified
            for value in n.values():
                walk(value)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(tree)
    return alias_map, sorted(relations)


def _split(qualified: str) -> tuple[str, str]:
    """(source, table) from a qualified relation, mirroring tools._mask_indices."""
    parts = qualified.split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "", parts[-1]


def _parse(sql: str) -> dict | None:
    con = duckdb.connect()
    try:
        raw = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
    except Exception:
        return None
    finally:
        con.close()
    try:
        tree = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if isinstance(tree, dict) and tree.get("error"):  # non-SELECT forms serialize to an error
        return None
    return tree
