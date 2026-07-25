"""Agent tools over the engine: catalog introspection + guarded querying with PII masking."""

from __future__ import annotations

import json
from typing import Any

from datacharter.contracts.access import resolve_masked
from datacharter.engine.session import Engine
from datacharter.models import QueryResult, Source

__all__ = ["ToolBox", "TOOL_SPECS"]

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_sources",
            "description": "List configured data sources with their types.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List all queryable tables with their fully-qualified relation names.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Show columns and types for one relation (e.g. 'crm.customers').",
            "parameters": {
                "type": "object",
                "properties": {"relation": {"type": "string"}},
                "required": ["relation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query",
            "description": (
                "Run a read-only SQL query and return rows. Use fully-qualified "
                "relation names. Prefer LIMIT for exploration."
            ),
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        },
    },
]

MASKED = "•••"
_MAX_TOOL_ROWS = 50


class ToolBox:
    """Executes tool calls against the engine; masks PII columns in returned data."""

    def __init__(
        self, engine: Engine, sources: list[Source], *, auto_pii: set[str] | None = None
    ) -> None:
        self._engine = engine
        # Column names flagged PII in any source's contract, matched case-insensitively.
        self._pii: set[str] = set()
        for src in sources:
            for cols in src.pii.values():
                self._pii.update(c.lower() for c in cols)
        self._auto_pii = auto_pii or set()
        # Per-source agent-access overrides (on=real, off=masked).
        self._overrides = {s.name: s.agent_access for s in sources if s.agent_access}

    async def run(self, name: str, arguments: str) -> str:
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return "Error: tool arguments were not valid JSON."
        handler = {
            "list_sources": self._list_sources,
            "list_tables": self._list_tables,
            "describe_table": self._describe_table,
            "query": self._query,
        }.get(name)
        if handler is None:
            return f"Error: unknown tool '{name}'."
        try:
            return await handler(args)
        except Exception as exc:  # engine errors already scrubbed; surface to the model
            return f"Error: {exc}"

    async def _list_sources(self, _args: dict) -> str:
        rows = [{"name": s.name, "type": s.type.value} for s in self._engine.sources]
        return json.dumps(rows)

    async def _list_tables(self, _args: dict) -> str:
        result = await self._engine.query("SHOW ALL TABLES", timeout_s=30)
        idx = {c: i for i, c in enumerate(result.columns)}
        out = []
        for row in result.rows:
            db = row[idx["database"]]
            if db in ("system", "temp"):
                continue
            table = row[idx["name"]]
            relation = table if db == "memory" else f"{db}.{table}"
            out.append({"relation": relation, "columns": list(row[idx["column_names"]])})
        return json.dumps(out)

    async def _describe_table(self, args: dict) -> str:
        relation = str(args.get("relation", ""))
        if not _is_safe_relation(relation):
            return "Error: invalid relation name."
        result = await self._engine.query(f"DESCRIBE {relation}", timeout_s=30)
        return self._render(result, set())  # schema is always visible; values masked only in query

    async def _query(self, args: dict) -> str:
        sql = str(args.get("sql", ""))
        result = await self._engine.query(sql, row_limit=_MAX_TOOL_ROWS)
        return self._render(result, self._mask_indices(result))

    def _masked(self, source: str, table: str, column: str) -> bool:
        return resolve_masked(
            source, table, column,
            declared_pii=self._pii, auto_pii=self._auto_pii, overrides=self._overrides,
        )

    def _mask_indices(self, result: QueryResult) -> set[int]:
        """Which output columns to mask. Prefer per-column lineage; when it's missing
        (e.g. SELECT *), resolve each column against the query's touched relations so
        agent-access overrides still apply; last resort is a name-based PII check."""
        prov = result.provenance or {}
        lineage = prov.get("lineage") or {}
        rels = []
        for r in prov.get("relations") or []:
            parts = str(r).split(".")
            if len(parts) >= 2:
                rels.append((parts[-2], parts[-1]))  # (source, table)
        idx = set()
        for i, outcol in enumerate(result.columns):
            srcs = lineage.get(outcol)
            if srcs:
                if any(self._lineage_masked(s) for s in srcs):
                    idx.add(i)
            elif rels:
                if any(self._masked(s, t, outcol) for (s, t) in rels):
                    idx.add(i)
            elif outcol.lower() in self._pii or outcol.lower() in self._auto_pii:
                idx.add(i)
        return idx

    def _lineage_masked(self, qualified: str) -> bool:
        parts = qualified.split(".")
        if len(parts) >= 3:
            return self._masked(parts[-3], parts[-2], parts[-1])
        name = parts[-1].lower()
        return name in self._pii or name in self._auto_pii

    def _render(self, result: QueryResult, mask_idx: set[int]) -> str:
        rows = [
            [MASKED if i in mask_idx else v for i, v in enumerate(row)]
            for row in result.rows
        ]
        payload = {
            "columns": result.columns,
            "rows": rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }
        if result.warnings:
            payload["warnings"] = result.warnings
        if result.provenance:
            payload["provenance"] = result.provenance
        if mask_idx:
            payload["masked_columns"] = [result.columns[i] for i in mask_idx]
        return json.dumps(payload, default=str)


def _is_safe_relation(relation: str) -> bool:
    parts = relation.split(".")
    return 1 <= len(parts) <= 3 and all(
        p and all(ch.isalnum() or ch == "_" for ch in p) for p in parts
    )
