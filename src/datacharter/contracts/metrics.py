"""Contract-scoped metrics: named, governed aggregations declared in charter.yaml.

A metric is a base relation + an aggregate expression (+ optional default
dimensions). It resolves to a single read-only SELECT so the agent and CLI hit a
governed definition instead of re-deriving SQL — a certified `revenue` always
means the same thing. This is a lightweight semantic layer; joins across sources
and time grains are a later refinement.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["Metric", "metric_sql", "MetricError"]


class MetricError(Exception):
    """A metric could not be resolved to SQL (bad relation or dimension)."""


class Metric(BaseModel):
    name: str
    relation: str
    expression: str
    dimensions: list[str] = Field(default_factory=list)


def _valid_identifier(name: str) -> bool:
    parts = name.split(".")
    return 1 <= len(parts) <= 3 and all(
        p and all(ch.isalnum() or ch == "_" for ch in p) for p in parts
    )


def metric_sql(metric: Metric, by: list[str] | None = None) -> str:
    """Resolve a metric to one read-only SELECT, grouped by `by` (or its defaults)."""
    dimensions = metric.dimensions if by is None else by
    if not _valid_identifier(metric.name):
        raise MetricError(f"metric '{metric.name}': invalid name")
    if not _valid_identifier(metric.relation):
        raise MetricError(f"metric '{metric.name}': invalid relation {metric.relation!r}")
    for dim in dimensions:
        if not _valid_identifier(dim):
            raise MetricError(f"metric '{metric.name}': invalid dimension {dim!r}")

    select = [*dimensions, f"{metric.expression} AS {metric.name}"]
    sql = f"SELECT {', '.join(select)} FROM {metric.relation}"
    if dimensions:
        grouped = ", ".join(dimensions)
        sql += f" GROUP BY {grouped} ORDER BY {grouped}"
    return sql
