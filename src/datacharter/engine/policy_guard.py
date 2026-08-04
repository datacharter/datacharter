"""Enforce charter policies on agent SQL: aggregate-only, k-anonymity, join limits.

Same fail-closed, DuckDB-parser approach as row_filter: queries we cannot analyze
confidently are refused with a message that tells the agent how to comply.
Enforcement is agent-surface only (ToolBox); the human editor is untouched.
"""

from __future__ import annotations

import json

import duckdb

from datacharter.contracts.policies import Policy
from datacharter.engine.provenance import extract_provenance

__all__ = ["PolicyRefusal", "check_policies", "apply_min_group"]

_K_ALIAS = "__dc_group_n"

_AGGREGATES = {
    "sum", "count", "count_star", "avg", "mean", "min", "max", "median",
    "stddev", "stddev_pop", "stddev_samp", "var_pop", "var_samp", "variance",
    "approx_count_distinct", "approx_quantile", "quantile", "quantile_cont",
    "quantile_disc", "mode", "bool_and", "bool_or", "bit_and", "bit_or",
    "arg_min", "arg_max", "first", "last", "string_agg", "list", "histogram",
}


class PolicyRefusal(Exception):
    """The query violates a charter policy; str() is the agent-facing message."""


def _refuse(msg: str) -> None:
    raise PolicyRefusal(f"Error: policy — {msg}")


def _matches(policy_key: str, relation: str) -> bool:
    # ATTACH sources register twice: the native `src.table` and a flat compat
    # view `src__table`. A policy on `src.table` must bind BOTH, or the agent
    # queries the alias and the policy never fires.
    pk = policy_key.lower().replace("__", ".")
    r = relation.lower().replace("__", ".")
    return pk == r or r.endswith("." + pk) or pk.endswith("." + r)


def _serialize(sql: str) -> dict | None:
    try:
        con = duckdb.connect(":memory:")
        try:
            raw = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
        finally:
            con.close()
        tree = json.loads(raw)
    except Exception:
        return None
    return None if not isinstance(tree, dict) or tree.get("error") else tree


def _is_aggregate_select(node: dict) -> bool:
    """True when the top-level SELECT can only emit aggregate rows."""
    if node.get("type") != "SELECT_NODE":
        return False
    if node.get("cte_map", {}).get("map"):
        return False  # CTEs: too many shapes to certify — keep it simple
    for mod in node.get("modifiers") or []:
        if "DISTINCT" in str(mod.get("type", "")):
            return False  # DISTINCT is row egress
    if node.get("group_expressions") or node.get("group_sets"):
        return True
    items = node.get("select_list") or []
    if not items:
        return False
    for item in items:
        cls = item.get("class")
        if cls == "CONSTANT":
            continue
        if cls == "FUNCTION" and item.get("function_name", "").lower() in _AGGREGATES \
                and not item.get("over"):
            continue
        return False
    return True


def check_policies(sql: str, policies: dict[str, Policy]) -> int | None:
    """Raise PolicyRefusal when `sql` violates a policy; return the strictest
    min_group_size to enforce (or None). Fail-closed for unanalyzable queries."""
    if not policies:
        return None
    prov = extract_provenance(sql)
    relations = [str(r) for r in (prov or {}).get("relations") or []]
    if not relations:
        # Cannot tell what this touches — refuse only if it might matter.
        _refuse(
            "this query is too complex to analyze against the workspace policies. "
            "Use a single plain SELECT over named tables."
        )
    touched: list[tuple[str, Policy, str]] = []  # (policy_key, policy, matched relation)
    for key, pol in policies.items():
        for rel in relations:
            if _matches(key, rel):
                touched.append((key, pol, rel))
                break
    if not touched:
        return None

    others = {r.lower() for r in relations}
    for key, pol, rel in touched:
        if pol.no_joins and len(relations) > 1:
            other = next(r for r in relations if not _matches(key, r))
            _refuse(f"`{rel}` may not be queried together with `{other}`.")
        for banned in pol.no_joins_to:
            hit = next((r for r in others if _matches(banned, r)), None)
            if hit is not None:
                _refuse(f"`{rel}` may not be queried together with `{hit}`.")

    needs_aggregate = [t for t in touched if t[1].aggregate_only or t[1].min_group_size]
    k = max((t[1].min_group_size or 0 for t in touched), default=0) or None
    if needs_aggregate:
        tree = _serialize(sql)
        stmts = (tree or {}).get("statements") or []
        rel = needs_aggregate[0][2]
        if tree is None or len(stmts) != 1 or not _is_aggregate_select(stmts[0].get("node", {})):
            _refuse(
                f"`{rel}` allows aggregates only. Write one plain SELECT with "
                "aggregate functions (and GROUP BY if needed) — no raw rows, "
                "DISTINCT, CTEs, or set operations."
            )
    return k


def apply_min_group(sql: str, k: int) -> str:
    """Rewrite an aggregate query so groups smaller than k are suppressed."""
    tree = _serialize(sql)
    if tree is None:
        raise PolicyRefusal("Error: policy — could not rewrite the query for k-anonymity.")
    template = _serialize(f'SELECT count(*) AS "{_K_ALIAS}"')
    counter = template["statements"][0]["node"]["select_list"][0]
    tree["statements"][0]["node"]["select_list"].append(counter)
    con = duckdb.connect(":memory:")
    try:
        inner = con.execute(
            "SELECT json_deserialize_sql(?)", [json.dumps(tree)]
        ).fetchone()[0]
    except Exception as exc:
        raise PolicyRefusal(
            "Error: policy — could not rewrite the query for k-anonymity."
        ) from exc
    finally:
        con.close()
    return (
        f'SELECT * EXCLUDE ("{_K_ALIAS}") FROM ({inner}) AS "__dc_k" '
        f'WHERE "{_K_ALIAS}" >= {int(k)}'
    )
