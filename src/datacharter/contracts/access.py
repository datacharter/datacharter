"""Resolve whether an agent-facing column is masked (access OFF) or real (ON).

Precedence: field override -> table override -> source override -> default (masked iff the
column is PII: declared or auto-detected). In the contract, `on` = real, `off` = masked.
"""

from __future__ import annotations


def build_overrides(sources, local_access: dict | None = None) -> dict:
    """The per-engine-source overrides map that `resolve_masked` consumes.

    ATTACH sources register under their charter name, so their overrides key
    directly. File and connector sources register under the engine's `memory`
    database (a plain view per table, or a `<source>__<table>` alias) — their
    overrides must be remapped there, else source/table toggles silently miss.
    A source-level toggle becomes per-table entries; explicit finer entries win.
    """
    from datacharter.models import ATTACH_TYPES

    overrides = {s.name: s.agent_access for s in sources if s.agent_access}
    if local_access:
        overrides["local"] = local_access

    mem_tables: dict = {}
    mem_columns: dict = {}
    for s in sources:
        if s.type in ATTACH_TYPES or not s.agent_access:
            continue
        aa = s.agent_access
        names = list(s.tables or [s.name])
        if "source" in aa:
            for t in names:
                for engine_name in (t, f"{s.name}__{t}"):
                    mem_tables.setdefault(engine_name, aa["source"])
        for t, v in (aa.get("tables") or {}).items():
            for engine_name in (t, f"{s.name}__{t}"):
                mem_tables[engine_name] = v
        for key, v in (aa.get("columns") or {}).items():
            t, _, c = key.partition(".")
            for engine_name in (t, f"{s.name}__{t}"):
                mem_columns[f"{engine_name}.{c}"] = v
    if mem_tables or mem_columns:
        mem = overrides.setdefault("memory", {})
        mem["tables"] = {**mem_tables, **(mem.get("tables") or {})}
        mem["columns"] = {**mem_columns, **(mem.get("columns") or {})}
    return overrides


def resolve_masked(
    source: str,
    table: str,
    column: str,
    *,
    declared_pii: set[str],
    auto_pii: set[str],
    overrides: dict,
) -> bool:
    """True if the agent should see this column masked (`•••`), False for real values."""
    src_ov = overrides.get(source) or {}
    columns = src_ov.get("columns") or {}
    key = f"{table}.{column}"
    if key in columns:
        return not columns[key]  # on -> not masked
    tables = src_ov.get("tables") or {}
    if table in tables:
        return not tables[table]
    if "source" in src_ov:
        return not src_ov["source"]
    col = column.lower()
    return col in declared_pii or col in auto_pii  # default: PII masked, else real
