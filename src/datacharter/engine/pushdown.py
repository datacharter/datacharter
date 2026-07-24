"""Deterministic filter/projection pushdown for connector-extract sources (D11).

DuckDB pushes predicates natively for ATTACH and file sources. Connector-extract
sources have no DuckDB scanner, so single-table filters/projections are computed
here from the query AST and folded into the remote extract SELECT — no agent.

Safety invariant: the caller's DuckDB query always re-applies the full WHERE
locally, so a conservative push (a subset of predicates, a superset of columns)
is always correct. When in doubt, push less.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

__all__ = ["Pushdown", "extract_pushdown"]

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# COMPARISON node type -> (operator, flipped operator for `const OP col`).
_COMPARE = {
    "COMPARE_EQUAL": ("=", "="),
    "COMPARE_NOTEQUAL": ("<>", "<>"),
    "COMPARE_LESSTHAN": ("<", ">"),
    "COMPARE_GREATERTHAN": (">", "<"),
    "COMPARE_LESSTHANOREQUALTO": ("<=", ">="),
    "COMPARE_GREATERTHANOREQUALTO": (">=", "<="),
}

_NUMERIC = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
}


@dataclass
class Pushdown:
    """Columns (None = all) and safe predicate fragments for one connector table."""

    columns: set[str] | None = None
    predicates: list[str] = field(default_factory=list)

    def select_sql(self, table: str, row_cap: int) -> str:
        """Remote extract SELECT with projection + filters folded in.

        Identifiers are pre-validated to `[A-Za-z_][A-Za-z0-9_]*`, so they are
        emitted unquoted — case-folding matches the remote's own default.
        """
        cols = "*" if self.columns is None else ", ".join(sorted(self.columns))
        where = f" WHERE {' AND '.join(self.predicates)}" if self.predicates else ""
        return f"SELECT {cols} FROM {table}{where} LIMIT {row_cap}"


def _ident(name: str | None) -> bool:
    return bool(name) and bool(_IDENT.match(name))


def _walk(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _col_parts(node: dict) -> tuple[str | None, str] | None:
    """(qualifier, column) for a COLUMN_REF node, else None."""
    if node.get("class") != "COLUMN_REF":
        return None
    names = node.get("column_names") or []
    if not names:
        return None
    return (names[-2] if len(names) >= 2 else None, names[-1])


def _literal(const: dict) -> str | None:
    """SQL literal for a CONSTANT node, or None if not safely representable."""
    value = const.get("value", {})
    if value.get("is_null"):
        return "NULL"
    type_id = (value.get("type") or {}).get("id", "")
    raw = value.get("value")
    if type_id in ("VARCHAR", "CHAR", "TEXT"):
        # These literals are sent to Snowflake, where backslash is an escape
        # char — double both backslash and quote so a value can't break out.
        escaped = str(raw).replace("\\", "\\\\").replace("'", "''")
        return "'" + escaped + "'"
    if type_id in _NUMERIC:
        return str(raw)
    if type_id == "BOOLEAN":
        return "TRUE" if raw else "FALSE"
    return None


def _predicate_for(node: dict) -> tuple[str | None, str] | None:
    """(qualifier, sql_fragment) for a whitelisted predicate, else None.

    The fragment uses the bare column name (remote query hits the raw table).
    """
    cls, typ = node.get("class"), node.get("type")
    if cls == "COMPARISON" and typ in _COMPARE:
        left, right = node.get("left", {}), node.get("right", {})
        if left.get("class") == "COLUMN_REF" and right.get("class") == "CONSTANT":
            col, const, op = left, right, _COMPARE[typ][0]
        elif left.get("class") == "CONSTANT" and right.get("class") == "COLUMN_REF":
            col, const, op = right, left, _COMPARE[typ][1]
        else:
            return None
        lit, parts = _literal(const), _col_parts(col)
        if lit is None or not parts or not _ident(parts[1]):
            return None
        return (parts[0], f"{parts[1]} {op} {lit}")
    if cls == "OPERATOR" and typ in ("OPERATOR_IS_NULL", "OPERATOR_IS_NOT_NULL"):
        kids = node.get("children", [])
        if len(kids) == 1 and (parts := _col_parts(kids[0])) and _ident(parts[1]):
            kw = "IS NULL" if typ == "OPERATOR_IS_NULL" else "IS NOT NULL"
            return (parts[0], f"{parts[1]} {kw}")
        return None
    if cls == "OPERATOR" and typ == "COMPARE_IN":
        kids = node.get("children", [])
        if len(kids) >= 2 and (parts := _col_parts(kids[0])) and _ident(parts[1]):
            lits = [_literal(k) for k in kids[1:] if k.get("class") == "CONSTANT"]
            if len(lits) == len(kids) - 1 and all(x is not None for x in lits):
                return (parts[0], f"{parts[1]} IN ({', '.join(lits)})")
        return None
    if cls == "FUNCTION" and node.get("function_name") in ("~~", "!~~"):
        kids = node.get("children", [])
        if (
            len(kids) == 2
            and (parts := _col_parts(kids[0]))
            and _ident(parts[1])
            and kids[1].get("class") == "CONSTANT"
            and (lit := _literal(kids[1])) is not None
        ):
            op = "LIKE" if node["function_name"] == "~~" else "NOT LIKE"
            return (parts[0], f"{parts[1]} {op} {lit}")
        return None
    return None


def _fallback(sql: str, connector_tables: set[str]) -> dict[str, Pushdown]:
    low = sql.lower()
    return {t: Pushdown() for t in connector_tables if t in low}


def extract_pushdown(
    conn: duckdb.DuckDBPyConnection, sql: str, connector_tables: set[str]
) -> dict[str, Pushdown]:
    """Map each referenced connector table -> its pushable projection + filters.

    `connector_tables` are the compat-view names as they appear in queries.
    Returns only tables the query references. Unparseable SQL falls back to a
    full extract for any connector table named in the text.
    """
    connector_tables = {t.lower() for t in connector_tables}
    if not connector_tables:
        return {}
    try:
        raw = conn.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
        stmt = json.loads(raw)["statements"][0]["node"]
    except Exception:
        return _fallback(sql, connector_tables)
    if not isinstance(stmt, dict):
        return _fallback(sql, connector_tables)

    # Base tables anywhere (subqueries included -> conservative table count).
    aliases: dict[str, str] = {}
    alias_count: dict[str, int] = {}
    total_tables = 0
    for node in _walk(stmt):
        if (
            isinstance(node, dict)
            and isinstance(node.get("table_name"), str)
            and node["table_name"]
        ):
            total_tables += 1
            real = node["table_name"].lower()
            eff = (node.get("alias") or node["table_name"]).lower()
            if real in connector_tables:
                aliases[eff] = real
                alias_count[real] = alias_count.get(real, 0) + 1

    referenced = set(aliases.values())
    if not referenced:
        return {}

    single = total_tables == 1 and len(referenced) == 1
    poisoned = {r for r, n in alias_count.items() if n > 1}  # self-join: don't push
    result = {r: (Pushdown() if r in poisoned else Pushdown(columns=set())) for r in referenced}

    def resolve(qualifier: str | None) -> str | None:
        if qualifier is not None:
            return aliases.get(qualifier.lower())
        return next(iter(referenced)) if single else None

    # Projection: every column ref / star across the statement.
    ambiguous = False
    for node in _walk(stmt):
        if not isinstance(node, dict):
            continue
        if node.get("class") == "STAR":
            rel = (node.get("relation_name") or "").lower()
            if not rel:
                for pushdown in result.values():
                    pushdown.columns = None
            elif rel in aliases:
                result[aliases[rel]].columns = None
        elif node.get("class") == "COLUMN_REF":
            parts = _col_parts(node)
            if not parts:
                continue
            real = resolve(parts[0])
            if real is None:
                ambiguous = ambiguous or parts[0] is None
                continue
            pushdown = result[real]
            if not _ident(parts[1]):
                pushdown.columns = None
            elif pushdown.columns is not None:
                pushdown.columns.add(parts[1])
    if ambiguous:
        for pushdown in result.values():
            pushdown.columns = None

    # Predicates: top-level WHERE conjuncts only.
    where = stmt.get("where_clause")
    if where:
        conjuncts = where["children"] if where.get("type") == "CONJUNCTION_AND" else [where]
        for cand in conjuncts:
            if not isinstance(cand, dict):
                continue
            pred = _predicate_for(cand)
            if pred is None:
                continue
            real = resolve(pred[0])
            if real is not None and real not in poisoned:
                result[real].predicates.append(pred[1])

    # Never select zero columns.
    for pushdown in result.values():
        if pushdown.columns is not None and not pushdown.columns:
            pushdown.columns = None
    return result
