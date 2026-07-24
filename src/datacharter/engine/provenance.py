"""Per-query provenance: the source relations and columns a read touches, plus
column lineage (each output column → the input columns that feed it).

Reuses DuckDB's parser (`json_serialize_sql`, the same tree the read-only guard
walks). Best-effort and informational: any parse failure yields `None`, never an
error. Lineage covers the top-level SELECT list; `SELECT *`, set operations, and
subquery-derived columns fall back to just the read set.
"""

from __future__ import annotations

import json

import duckdb

__all__ = ["extract_provenance"]


def extract_provenance(sql: str) -> dict | None:
    """Return `{"relations", "columns", "lineage"?}` for a read, or None.

    `relations` and `columns` are the read set; `lineage` (present only when it
    can be computed) maps each output column to its input columns.
    """
    tree = _parse(sql)
    if tree is None:
        return None

    tables: list[tuple[str, str]] = []  # (alias-or-name, qualified relation)
    column_refs: list[list[str]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "BASE_TABLE":
                qualified = ".".join(
                    p
                    for p in (
                        node.get("catalog_name"),
                        node.get("schema_name"),
                        node.get("table_name"),
                    )
                    if p
                )
                if qualified:
                    tables.append((node.get("alias") or node.get("table_name"), qualified))
            elif node.get("type") == "COLUMN_REF":
                names = node.get("column_names")
                if isinstance(names, list) and names:
                    column_refs.append(names)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(tree)
    if not tables:
        return None

    relations = sorted({q for _, q in tables})
    alias_map = {alias: q for alias, q in tables}
    result: dict = {
        "relations": relations,
        "columns": sorted({_resolve(names, alias_map, relations) for names in column_refs}),
    }
    lineage = _lineage(tree, alias_map, relations)
    if lineage:
        result["lineage"] = lineage
    return result


def _resolve(names: list[str], alias_map: dict[str, str], relations: list[str]) -> str:
    """Qualify a column reference to `relation.column` where the reference (or a
    single-table query) makes the source unambiguous."""
    col = names[-1]
    qualifier = names[-2] if len(names) >= 2 else None
    if qualifier in alias_map:
        return f"{alias_map[qualifier]}.{col}"
    if qualifier:
        return f"{qualifier}.{col}"
    if len(relations) == 1:
        return f"{relations[0]}.{col}"
    return col


def _lineage(tree: dict, alias_map: dict[str, str], relations: list[str]) -> dict[str, list[str]]:
    statements = tree.get("statements") if isinstance(tree, dict) else None
    node = statements[0].get("node") if statements else None
    if not isinstance(node, dict) or node.get("type") != "SELECT_NODE":
        return {}
    out: dict[str, list[str]] = {}
    for entry in node.get("select_list") or []:
        name = entry.get("alias") or ""
        if not name and entry.get("type") == "COLUMN_REF":
            cols = entry.get("column_names") or []
            name = cols[-1] if cols else ""
        if not name:
            continue  # a `*` or an unnameable expression — skip rather than guess
        refs: list[list[str]] = []
        _collect_column_refs(entry, refs)
        out[name] = sorted({_resolve(ref, alias_map, relations) for ref in refs})
    return out


def _collect_column_refs(node: object, out: list[list[str]]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "COLUMN_REF":
            names = node.get("column_names")
            if isinstance(names, list) and names:
                out.append(names)
        for value in node.values():
            _collect_column_refs(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_column_refs(item, out)


def _parse(sql: str) -> object | None:
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
