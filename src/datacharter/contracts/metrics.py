"""Contract-scoped metrics: named, governed aggregations declared in charter.yaml.

A metric is a base relation + an aggregate expression (+ optional default
dimensions). It resolves to a single read-only SELECT so the agent and CLI hit a
governed definition instead of re-deriving SQL — a certified `revenue` always
means the same thing. This is a lightweight semantic layer; joins across sources
and time grains are a later refinement.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["Metric", "MetricJoin", "metric_sql", "MetricError"]

_GRAINS = {"day", "week", "month", "quarter", "year"}
_JOIN_TYPES = {"inner", "left", "right", "full"}


class MetricError(Exception):
    """A metric could not be resolved to SQL (bad relation, dimension, join, or grain)."""


class MetricJoin(BaseModel):
    relation: str
    on: str
    type: str = "inner"


class Metric(BaseModel):
    name: str
    relation: str
    expression: str
    dimensions: list[str] = Field(default_factory=list)
    joins: list[MetricJoin] = Field(default_factory=list)
    time_column: str | None = None


def _valid_identifier(name: str) -> bool:
    parts = name.split(".")
    return 1 <= len(parts) <= 3 and all(
        p and all(ch.isalnum() or ch == "_" for ch in p) for p in parts
    )


def metric_sql(metric: Metric, by: list[str] | None = None, grain: str | None = None) -> str:
    """Resolve a metric to one read-only SELECT — with optional joins + time grain.

    `expression` and each join `on` are raw SQL (trusted contract config); every
    identifier (relation, joins, dimensions, time_column) and the grain/join type
    are validated.
    """
    dimensions = metric.dimensions if by is None else by
    if not _valid_identifier(metric.name):
        raise MetricError(f"metric '{metric.name}': invalid name")
    if not _valid_identifier(metric.relation):
        raise MetricError(f"metric '{metric.name}': invalid relation {metric.relation!r}")
    for dim in dimensions:
        if not _valid_identifier(dim):
            raise MetricError(f"metric '{metric.name}': invalid dimension {dim!r}")

    from_sql = metric.relation
    for j in metric.joins:
        if j.type not in _JOIN_TYPES:
            raise MetricError(f"metric '{metric.name}': invalid join type {j.type!r}")
        if not _valid_identifier(j.relation):
            raise MetricError(f"metric '{metric.name}': invalid join relation {j.relation!r}")
        from_sql += f" {j.type.upper()} JOIN {j.relation} ON {j.on}"

    dim_exprs = list(dimensions)
    select = list(dimensions)
    if grain is not None:
        if grain not in _GRAINS:
            raise MetricError(f"metric '{metric.name}': invalid grain {grain!r}")
        if not metric.time_column or not _valid_identifier(metric.time_column):
            raise MetricError(f"metric '{metric.name}': --grain needs a valid time_column")
        # CAST: date columns are often TEXT in sqlite/CSV sources; date_trunc
        # takes no VARCHAR, and TIMESTAMP accepts ISO date strings and DATEs alike.
        trunc = f"date_trunc('{grain}', CAST({metric.time_column} AS TIMESTAMP))"
        alias = metric.time_column.split(".")[-1]
        dim_exprs.insert(0, trunc)
        select.insert(0, f"{trunc} AS {alias}")

    select.append(f"{metric.expression} AS {metric.name}")
    sql = f"SELECT {', '.join(select)} FROM {from_sql}"
    if dim_exprs:
        grouped = ", ".join(dim_exprs)
        sql += f" GROUP BY {grouped} ORDER BY {grouped}"
    return sql
