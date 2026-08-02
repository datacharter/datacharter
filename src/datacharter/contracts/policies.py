"""Plain-English data policies: a tiny controlled grammar, compiled deterministically.

`policies:` in charter.yaml accepts sentences ("aggregates only", "groups of at
least 10", "no joins to payments") or the equivalent structured keys. Sentences
are matched by exact regex — anything unrecognized is a load error, so there is
no ambiguity and no model in the loop. Enforcement lives in engine/policy_guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from datacharter.contracts.loader_errors import CharterError

__all__ = ["Policy", "parse_policies", "render_sentences"]


@dataclass
class Policy:
    aggregate_only: bool = False
    min_group_size: int | None = None
    no_joins: bool = False
    no_joins_to: set[str] = field(default_factory=set)


_AGG = re.compile(r"^(aggregates only|agents may only read aggregates)$", re.I)
_K = re.compile(r"^groups of (?:at least (\d+)|(\d+) or more)$", re.I)
_NOJOIN = re.compile(r"^no joins$", re.I)
_NOJOIN_TO = re.compile(r"^(?:no joins to|never join to)\s+(.+)$", re.I)


def _apply_sentence(policy: Policy, sentence: str, ctx: str) -> None:
    s = sentence.strip()
    if _AGG.match(s):
        policy.aggregate_only = True
        return
    m = _K.match(s)
    if m:
        k = int(m.group(1) or m.group(2))
        if k < 2:
            raise CharterError(f"{ctx}: 'groups of at least {k}' — k must be 2 or more.")
        policy.min_group_size = k
        return
    if _NOJOIN.match(s):
        policy.no_joins = True
        return
    m = _NOJOIN_TO.match(s)
    if m:
        rels = {r.strip().lower() for r in m.group(1).split(",") if r.strip()}
        if not rels:
            raise CharterError(f"{ctx}: 'no joins to' needs at least one relation.")
        policy.no_joins_to |= rels
        return
    raise CharterError(
        f"{ctx}: unrecognized policy sentence {sentence!r}. Known forms: "
        "'aggregates only' · 'groups of at least N' · 'no joins' · 'no joins to a, b'."
    )


_KEYS = {"aggregate_only", "min_group_size", "no_joins", "no_joins_to"}


def _apply_structured(policy: Policy, body: dict, ctx: str) -> None:
    for key in body:
        if key not in _KEYS:
            raise CharterError(f"{ctx}: unknown policy key {key!r} (known: {sorted(_KEYS)}).")
    if "aggregate_only" in body:
        policy.aggregate_only = bool(body["aggregate_only"])
    if "min_group_size" in body:
        k = body["min_group_size"]
        if not isinstance(k, int) or k < 2:
            raise CharterError(f"{ctx}: min_group_size must be an integer ≥ 2 (got {k!r}).")
        policy.min_group_size = k
    if "no_joins" in body:
        policy.no_joins = bool(body["no_joins"])
    if "no_joins_to" in body:
        rels = body["no_joins_to"]
        if not isinstance(rels, list) or not all(isinstance(r, str) for r in rels):
            raise CharterError(f"{ctx}: no_joins_to must be a list of relation names.")
        policy.no_joins_to |= {r.lower() for r in rels}


def parse_policies(raw: dict) -> dict[str, Policy]:
    if not isinstance(raw, dict):
        raise CharterError("'policies' must be a mapping of relation -> rules.")
    out: dict[str, Policy] = {}
    for rel, value in raw.items():
        ctx = f"policies.{rel}"
        policy = Policy()
        if isinstance(value, dict):
            _apply_structured(policy, value, ctx)
        elif isinstance(value, list):
            for sentence in value:
                if not isinstance(sentence, str):
                    raise CharterError(f"{ctx}: policy entries must be sentences or a mapping.")
                _apply_sentence(policy, sentence, ctx)
        elif isinstance(value, str):
            _apply_sentence(policy, value, ctx)
        else:
            raise CharterError(f"{ctx}: must be a sentence, list of sentences, or mapping.")
        out[str(rel).lower()] = policy
    return out


def render_sentences(policy: Policy) -> list[str]:
    """Canonical English for a policy — shown to agents in describe_table."""
    out: list[str] = []
    if policy.aggregate_only:
        out.append("aggregates only")
    if policy.min_group_size:
        out.append(f"groups of at least {policy.min_group_size}")
    if policy.no_joins:
        out.append("no joins")
    if policy.no_joins_to:
        out.append("no joins to " + ", ".join(sorted(policy.no_joins_to)))
    return out
