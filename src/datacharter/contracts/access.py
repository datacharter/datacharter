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
        if not s.agent_access:
            continue
        aa = s.agent_access
        names = list(s.tables or [s.name])
        # Every source exposes a flat compat view `src__table` under `memory`;
        # ATTACH sources ALSO answer to native `src.table` (covered by the
        # source-name key above). File/connector sources register the bare
        # table name as their memory view. Both engine spellings must inherit
        # the override or the agent queries the ungoverned one.
        is_attach = s.type in ATTACH_TYPES

        def engine_names(t: str, attach: bool = is_attach, name: str = s.name):
            yield f"{name}__{t}"
            if not attach:
                yield t

        if "source" in aa:
            for t in names:
                for engine_name in engine_names(t):
                    mem_tables.setdefault(engine_name, aa["source"])
        for t, v in (aa.get("tables") or {}).items():
            for engine_name in engine_names(t):
                mem_tables[engine_name] = v
        for key, v in (aa.get("columns") or {}).items():
            t, _, c = key.partition(".")
            for engine_name in engine_names(t):
                mem_columns[f"{engine_name}.{c}"] = v
    # `local_access` also governs uploaded tables (they live under `memory`
    # with no charter source to hang overrides on) — charter-derived entries
    # keep precedence.
    if local_access:
        for t, v in (local_access.get("tables") or {}).items():
            mem_tables.setdefault(t, v)
        for key, v in (local_access.get("columns") or {}).items():
            mem_columns.setdefault(key, v)

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
    """True if the agent should see this column masked (`•••`), False for real values.

    All relation/column matching is case-insensitive: DuckDB resolves
    identifiers case-insensitively, so `crm.Customers` and `crm.customers` are
    the same table — a mixed-case spelling must not slip past an override.
    """
    src_ov = _ci_get(overrides, source) or {}
    columns = src_ov.get("columns") or {}
    col_ov = _ci_get(columns, f"{table}.{column}")
    if col_ov is not None:
        return not col_ov  # on -> not masked
    tables = src_ov.get("tables") or {}
    tbl_ov = _ci_get(tables, table)
    if tbl_ov is not None:
        return not tbl_ov
    if "source" in src_ov:
        return not src_ov["source"]
    col = column.lower()
    return col in declared_pii or col in auto_pii  # default: PII masked, else real


def _ci_get(mapping: dict, key: str):
    """Case-insensitive dict lookup (identifiers compare case-insensitively)."""
    if key in mapping:
        return mapping[key]
    low = key.lower()
    for k, v in mapping.items():
        if k.lower() == low:
            return v
    return None
