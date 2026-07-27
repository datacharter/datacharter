"""Declarative data assertions: compile a charter test to a query whose single
integer result is the number of failing rows (0 = pass)."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["DataTest", "DataTestError", "check_sql"]

_TYPES = {"not_null", "unique", "accepted_values", "row_count", "expression"}


class DataTestError(Exception):
    """A data test could not be compiled (bad type, missing param, or bad identifier)."""


class DataTest(BaseModel):
    name: str
    type: str
    relation: str
    column: str | None = None
    columns: list[str] = Field(default_factory=list)
    values: list = Field(default_factory=list)
    min: int | None = None
    max: int | None = None
    expression: str | None = None


def _ident(name: str) -> bool:
    parts = str(name).split(".")
    return 1 <= len(parts) <= 3 and all(
        p and all(ch.isalnum() or ch == "_" for ch in p) for p in parts
    )


def _literal(v: object) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    raise DataTestError(f"unsupported accepted_values literal: {v!r}")


def check_sql(test: DataTest) -> str:
    """Compile a test to a SELECT returning one integer = failing rows (0 = pass)."""
    name = test.name
    if test.type not in _TYPES:
        raise DataTestError(f"test '{name}': unknown type {test.type!r}")
    if not _ident(test.relation):
        raise DataTestError(f"test '{name}': invalid relation {test.relation!r}")
    rel = test.relation

    if test.type == "not_null":
        if not test.column or not _ident(test.column):
            raise DataTestError(f"test '{name}': not_null needs a valid 'column'")
        return f"SELECT count(*) FROM {rel} WHERE {test.column} IS NULL"

    if test.type == "unique":
        cols = test.columns or ([test.column] if test.column else [])
        if not cols or not all(_ident(c) for c in cols):
            raise DataTestError(f"test '{name}': unique needs valid 'columns'")
        keys = ", ".join(cols)
        return f"SELECT count(*) FROM (SELECT 1 FROM {rel} GROUP BY {keys} HAVING count(*) > 1) t"

    if test.type == "accepted_values":
        if not test.column or not _ident(test.column):
            raise DataTestError(f"test '{name}': accepted_values needs a valid 'column'")
        if not test.values:
            raise DataTestError(f"test '{name}': accepted_values needs 'values'")
        vals = ", ".join(_literal(v) for v in test.values)
        return (
            f"SELECT count(*) FROM {rel} "
            f"WHERE {test.column} IS NOT NULL AND {test.column} NOT IN ({vals})"
        )

    if test.type == "expression":
        if not test.expression:
            raise DataTestError(f"test '{name}': expression needs an 'expression'")
        return f"SELECT count(*) FROM {rel} WHERE NOT ({test.expression})"

    # row_count
    if test.min is None and test.max is None:
        raise DataTestError(f"test '{name}': row_count needs 'min' and/or 'max'")
    conds = []
    if test.min is not None:
        conds.append(f"c < {int(test.min)}")
    if test.max is not None:
        conds.append(f"c > {int(test.max)}")
    cond = " OR ".join(conds)
    return f"SELECT CASE WHEN {cond} THEN 1 ELSE 0 END FROM (SELECT count(*) c FROM {rel}) t"
