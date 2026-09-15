"""Wrap ToolBox so an authenticated principal only sees granted relations."""

from __future__ import annotations

import json
import re

from datacharter.contracts.grants import CharterPolicy
from datacharter.engine.provenance import extract_provenance
from datacharter.mcp.auth import Principal

__all__ = ["GovernedToolBox"]

_FROM = re.compile(r"\bfrom\b", re.I)


def _split_rel(rel: str) -> tuple[str, str]:
    parts = [p for p in rel.split(".") if p]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    name = parts[0] if parts else ""
    return name, name


def _split_col(col: str, relations: list[str]) -> list[tuple[str, str, str]]:
    """Map a provenance column to (source, table, column) candidates."""
    parts = [p for p in col.split(".") if p]
    if len(parts) >= 3:
        return [(parts[0], parts[1], parts[-1])]
    if len(parts) == 2:
        return [(parts[0], parts[0], parts[1]), (parts[0], parts[1], parts[1])]
    column = parts[0] if parts else col
    out = []
    for rel in relations:
        source, table = _split_rel(rel)
        out.append((source, table, column))
    return out or [("", "", column)]


class GovernedToolBox:
    """Same run() contract as ToolBox; prunes catalog and refuses unauthorized SQL."""

    def __init__(self, inner, principal: Principal, policy: CharterPolicy) -> None:
        self._inner = inner
        self._principal = principal
        self._policy = policy
        self.recorder = getattr(inner, "recorder", None)
        self.guides = getattr(inner, "guides", "")
        self.canary = getattr(inner, "canary", None)

    async def run(self, name: str, arguments: str) -> str:
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return await self._inner.run(name, arguments)
        if name == "list_sources":
            return await self._list_sources(arguments)
        if name == "list_tables":
            return await self._list_tables(arguments)
        if name == "describe_table":
            return await self._describe_table(args, arguments)
        if name == "query":
            denied = self._authorize_sql(str(args.get("sql", "")))
            if denied:
                return self._deny(name, arguments, denied)
            return await self._inner.run(name, arguments)
        if name == "list_metrics":
            return await self._list_metrics(arguments)
        if name == "query_metric":
            return await self._query_metric(args, arguments)
        return await self._inner.run(name, arguments)

    def _ok(self, source: str, table: str | None = None, column: str | None = None) -> bool:
        return self._policy.permits(self._principal, source, table, column)

    def _deny(self, name: str, arguments: str, message: str) -> str:
        rec = self.recorder
        if rec is not None:
            rec.record_access(name, arguments, message)
        return message

    async def _list_sources(self, arguments: str) -> str:
        raw = await self._inner.run("list_sources", arguments)
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        kept = [r for r in rows if self._ok(str(r.get("name", "")))]
        return json.dumps(kept)

    async def _list_tables(self, arguments: str) -> str:
        raw = await self._inner.run("list_tables", arguments)
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        kept = []
        for row in rows:
            rel = str(row.get("relation", ""))
            source, table = _split_rel(rel)
            if not self._ok(source, table):
                continue
            cols = [
                c
                for c in (row.get("columns") or [])
                if self._ok(source, table, str(c))
            ]
            kept.append({**row, "columns": cols})
        return json.dumps(kept)

    async def _describe_table(self, args: dict, arguments: str) -> str:
        rel = str(args.get("relation", ""))
        source, table = _split_rel(rel)
        if not self._ok(source, table):
            return self._deny(
                "describe_table", arguments, f"Error: not authorized to describe {rel}."
            )
        raw = await self._inner.run("describe_table", arguments)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        rows = payload.get("rows")
        cols = payload.get("columns") or []
        if not isinstance(rows, list) or "column_name" not in cols:
            return raw
        name_i = cols.index("column_name")
        payload["rows"] = [
            r for r in rows if isinstance(r, list) and self._ok(source, table, str(r[name_i]))
        ]
        return json.dumps(payload, default=str)

    async def _list_metrics(self, arguments: str) -> str:
        raw = await self._inner.run("list_metrics", arguments)
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if not isinstance(rows, list):
            return raw
        kept = []
        for row in rows:
            rel = str(row.get("relation", ""))
            source, table = _split_rel(rel)
            if self._ok(source, table):
                kept.append(row)
        return json.dumps(kept)

    async def _query_metric(self, args: dict, arguments: str) -> str:
        raw_list = await self._inner.run("list_metrics", "{}")
        try:
            metrics = json.loads(raw_list)
        except json.JSONDecodeError:
            metrics = []
        name = str(args.get("name", "")).strip().lower()
        for row in metrics if isinstance(metrics, list) else []:
            if str(row.get("name", "")).lower() == name:
                rel = str(row.get("relation", ""))
                source, table = _split_rel(rel)
                if not self._ok(source, table):
                    return self._deny(
                        "query_metric",
                        arguments,
                        f"Error: not authorized to query metric '{name}'.",
                    )
                break
        return await self._inner.run("query_metric", arguments)

    def _authorize_sql(self, sql: str) -> str | None:
        prov = extract_provenance(sql)
        if prov is None:
            if _FROM.search(sql):
                return "Error: not authorized to run this query."
            return None
        relations = list(prov.get("relations") or [])
        for rel in relations:
            source, table = _split_rel(str(rel))
            if not self._ok(source, table):
                return f"Error: not authorized to query {rel}."
        for col in prov.get("columns") or []:
            candidates = _split_col(str(col), relations)
            if str(col) and not any(self._ok(s, t, c) for s, t, c in candidates if c):
                return f"Error: not authorized to query column {col}."
        return None
