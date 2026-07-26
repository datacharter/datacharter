"""Row-level security for the agent surface: rewrite a read so each referenced
table with a contract row-filter is wrapped in a filtered subquery. Fail-closed.

Uses DuckDB's parser (`json_serialize_sql` / `json_deserialize_sql`) on an
ephemeral connection — the same approach as the read-only guard and provenance.
"""

from __future__ import annotations

import json

import duckdb

__all__ = ["apply_row_filters", "RowFilterError"]


class RowFilterError(Exception):
    """A filtered table is referenced but the query could not be safely rewritten."""


def _serialize(con: duckdb.DuckDBPyConnection, sql: str) -> dict | None:
    try:
        tree = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    except Exception:
        return None
    return None if isinstance(tree, dict) and tree.get("error") else tree


def _subquery_node(con: duckdb.DuckDBPyConnection, table: str, predicate: str, alias: str):
    tmpl = f'SELECT * FROM (SELECT * FROM "{table}" WHERE {predicate}) AS "{alias}"'
    tree = _serialize(con, tmpl)
    if tree is None:
        raise RowFilterError(f"Invalid row_filter for '{table}': {predicate!r}")
    return tree["statements"][0]["node"]["from_table"]


def apply_row_filters(sql: str, filters: dict[str, str]) -> str:
    """Return `sql` with every referenced filtered table wrapped as
    `(SELECT * FROM <table> WHERE <predicate>) AS <alias>`. Unchanged when no
    filtered table is referenced; raises RowFilterError (fail-closed) when one is
    referenced but the rewrite can't be produced."""
    if not filters:
        return sql
    con = duckdb.connect()
    try:
        tree = _serialize(con, sql)
        if tree is None:
            # Can't inspect it — only fail-closed if it plausibly names a filtered table.
            low = sql.lower()
            if any(t.lower() in low for t in filters):
                raise RowFilterError("Could not rewrite query to apply row filters.")
            return sql
        touched = {"hit": False}

        def walk(node: object) -> object:
            if isinstance(node, dict):
                if node.get("type") == "BASE_TABLE":
                    name = node.get("table_name")
                    pred = filters.get(name) if name else None
                    if pred is not None:
                        touched["hit"] = True
                        alias = node.get("alias") or name
                        return _subquery_node(con, name, pred, alias)
                return {k: walk(v) for k, v in node.items()}
            if isinstance(node, list):
                return [walk(x) for x in node]
            return node

        rewritten = walk(tree)
        if not touched["hit"]:
            return sql
        try:
            return con.execute(
                "SELECT json_deserialize_sql(?)", [json.dumps(rewritten)]
            ).fetchone()[0]
        except Exception as exc:
            raise RowFilterError("Could not rewrite query to apply row filters.") from exc
    finally:
        con.close()
