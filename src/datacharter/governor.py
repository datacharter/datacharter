"""The Reasoning Governor: turn a query's intent, declared purpose, and data
sensitivity into one graduated decision — allow, mask-more, add-noise, step-up, or
deny-with-reason.

Static RBAC answers "may this principal read this column?". It cannot answer "this
principal may read it, but *this* query — a whole-row serialization for an export
purpose — should be denied". The governor sits on the query shape (via the intent
`risk` scorer) plus the purpose and the PII touched, and picks the least-restrictive
action that still holds the line. Every decision carries a reason and a concrete
next step, so an agent gets actionable feedback instead of an opaque 403.
"""

from __future__ import annotations

from dataclasses import dataclass

from datacharter.dp import is_aggregate
from datacharter.risk import RiskAssessment, score_query

__all__ = ["Action", "Decision", "govern", "ACTIONS"]

# Ordered least → most restrictive.
ACTIONS = ("allow", "add_noise", "mask_more", "step_up", "deny")


class Action:
    ALLOW = "allow"
    ADD_NOISE = "add_noise"
    MASK_MORE = "mask_more"
    STEP_UP = "step_up"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    recommendation: str
    risk: RiskAssessment

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "recommendation": self.recommendation,
            "risk": self.risk.to_dict(),
        }


def _has(risk: RiskAssessment, signal: str) -> bool:
    return any(s.name == signal for s in risk.signals)


def govern(
    sql: str, *, pii_columns: set[str] | None = None, canaries: set[str] | None = None,
    purpose: str | None = None, has_policies: bool = False,
) -> Decision:
    """Reason about the query and return the graduated decision. Rules run in
    priority order; the first that fires wins (most-restrictive concerns first)."""
    risk = score_query(sql, pii_columns=pii_columns, canaries=canaries)
    names_pii = _has(risk, "pii_columns")
    purpose = (purpose or "").strip().lower()

    if _has(risk, "canary_reference"):
        return Decision(Action.DENY,
                        "the query references a honeytoken — this looks like probing",
                        "no honeytoken is ever real data; investigate the caller", risk)

    if risk.band == "high":
        top = ", ".join(s.name for s in risk.signals[:3])
        return Decision(Action.DENY,
                        f"intent risk is high ({risk.score}/100): {top}",
                        "narrow the query — filter rows, drop PII columns, or aggregate", risk)

    if purpose in ("export", "extract", "download", "share") and names_pii:
        return Decision(Action.DENY,
                        f"purpose '{purpose}' over PII is a bulk-exfiltration shape",
                        "request an aggregate or a governed `seal-data` extract instead", risk)

    if _has(risk, "row_serialization"):
        return Decision(Action.MASK_MORE,
                        "whole-row serialization can evade column masking",
                        "select named columns; masking is enforced on the surface", risk)

    if names_pii and is_aggregate(sql):
        return Decision(Action.ADD_NOISE,
                        "aggregating over PII can difference-out individuals",
                        "answer under differential privacy: `datacharter dp <sql>`", risk)

    if risk.band == "medium":
        top = ", ".join(s.name for s in risk.signals[:3])
        return Decision(Action.STEP_UP,
                        f"elevated intent ({risk.score}/100): {top}",
                        "require step-up auth / a stated purpose before answering", risk)

    return Decision(Action.ALLOW,
                    "narrow, filtered read with no elevated-intent signals",
                    "proceed", risk)
