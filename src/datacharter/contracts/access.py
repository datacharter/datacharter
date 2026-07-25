"""Resolve whether an agent-facing column is masked (access OFF) or real (ON).

Precedence: field override -> table override -> source override -> default (masked iff the
column is PII: declared or auto-detected). In the contract, `on` = real, `off` = masked.
"""

from __future__ import annotations


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
