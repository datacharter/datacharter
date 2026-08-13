"""Query-intent risk scoring: grade *how risky a query's shape is* before it runs,
so a governed surface can graduate its response (log, step-up, deny) by intent —
something static table/column RBAC can't express.

This is a transparent heuristic, not a guarantee: every signal carries a named
weight and the total is capped at 100. It reads the SQL text and the contract's PII
list — no data — so it is cheap enough to run on every request. The Reasoning
Governor (see docs) consumes this score to pick an action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Signal", "RiskAssessment", "score_query", "BANDS"]

BANDS = ("low", "medium", "high")

# Whole-row / column serialization functions — the classic "wrap the value so
# masking-by-column-name misses it, then read it all out" exfiltration shape.
_SERIALIZE = re.compile(
    r"\b(to_json|row_to_json|string_agg|array_agg|list\s*\(|json_group|group_concat)\b|::json",
    re.IGNORECASE,
)
_SELECT_STAR = re.compile(r"select\s+\*", re.IGNORECASE)
_HAS_WHERE = re.compile(r"\bwhere\b", re.IGNORECASE)
_HAS_LIMIT = re.compile(r"\blimit\b", re.IGNORECASE)
_HAS_AGG = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)
_SET_OP = re.compile(r"\b(union|except|intersect)\b", re.IGNORECASE)
_JOIN = re.compile(r"\bjoin\b", re.IGNORECASE)


@dataclass(frozen=True)
class Signal:
    name: str
    weight: int
    detail: str


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    band: str
    signals: list[Signal]

    def to_dict(self) -> dict:
        return {
            "score": self.score, "band": self.band,
            "signals": [{"name": s.name, "weight": s.weight, "detail": s.detail}
                        for s in self.signals],
        }


def _band(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def score_query(
    sql: str, *, pii_columns: set[str] | None = None, canaries: set[str] | None = None,
) -> RiskAssessment:
    """Score a query's intent from its shape and the columns it names."""
    pii = {c.lower() for c in (pii_columns or set())}
    canary = {c.lower() for c in (canaries or set())}
    low = sql.lower()
    signals: list[Signal] = []

    if _SELECT_STAR.search(sql):
        signals.append(Signal("select_star", 15, "selects every column (broad exposure)"))

    named_pii = sorted(c for c in pii if re.search(rf"\b{re.escape(c)}\b", low))
    if named_pii:
        w = min(40, 20 * len(named_pii))
        signals.append(Signal("pii_columns", w, f"names PII column(s): {', '.join(named_pii)}"))

    if _SERIALIZE.search(sql):
        signals.append(Signal(
            "row_serialization", 25,
            "serializes rows/columns (to_json/string_agg/…) — a masking-evasion pattern"))

    hit_canary = sorted(c for c in canary if re.search(rf"\b{re.escape(c)}\b", low))
    if hit_canary:
        signals.append(Signal("canary_reference", 40,
                              f"references a honeytoken name: {', '.join(hit_canary)}"))

    if _SET_OP.search(sql):
        signals.append(Signal("set_operation", 10,
                              "set operation (union/except) — a differencing shape"))

    joins = len(_JOIN.findall(sql))
    if joins >= 2 and named_pii:
        signals.append(Signal("multi_join_pii", 15,
                              f"{joins} joins while reading PII — re-identification risk"))

    # Bulk read: no filter, no aggregate, no limit → pull the whole table.
    if not _HAS_WHERE.search(sql) and not _HAS_AGG.search(sql) and not _HAS_LIMIT.search(sql):
        signals.append(Signal("unbounded_read", 15,
                              "no WHERE / aggregate / LIMIT — reads the whole relation"))

    score = min(100, sum(s.weight for s in signals))
    return RiskAssessment(score, _band(score), signals)
