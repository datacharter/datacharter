"""Access Plan — a `terraform plan` for AI data access.

Every competitor's governance is runtime state in a server; DataCharter's is a
file in git. This module makes that difference reviewable: it derives the
*effective agent-visible surface* from a charter (declared governance only — no
source connection, so it runs offline and in CI) and diffs two versions into
plain-English WIDENED / NARROWED / NEUTRAL changes. `--fail-on widened` turns
the existing GitHub Action into a merge gate that blocks a PR quietly widening
what an agent can see.

Fail closed: any structural change we cannot classify is reported WIDENED.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from datacharter.contracts.loader import Charter
from datacharter.contracts.policies import Policy

__all__ = ["Change", "effective_surface", "surface_hash", "diff_surfaces", "render_changes"]

WIDENED = "WIDENED"
NARROWED = "NARROWED"
NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class Change:
    """One classified difference between two access surfaces."""

    kind: str  # WIDENED | NARROWED | NEUTRAL
    path: str  # e.g. "store.customers.email" — where the change is
    detail: str  # plain-English description


def _policy_dict(policy: Policy) -> dict:
    return {
        "aggregate_only": policy.aggregate_only,
        "min_group_size": policy.min_group_size,
        "no_joins": policy.no_joins,
        "no_joins_to": sorted(policy.no_joins_to),
    }


def effective_surface(charter: Charter) -> dict:
    """Canonical, JSON-stable structure of what an agent can see.

    Declared governance only: source/table/column access toggles, declared PII
    (masked by default), row filters, and policies. Column *values* and the full
    column list require a live connection and are deliberately out of scope —
    the surface is the reviewable intent, not the data.
    """
    sources: dict = {}
    for src in charter.sources:
        aa = src.agent_access or {}
        # Union every table named anywhere in this source's governance. Lowercase
        # everything: DuckDB matches identifiers case-insensitively, so `Orders`
        # and `orders` are one table — not lowercasing split them and swallowed a
        # PII removal as a spurious "table removed".
        table_names: set[str] = {t.lower() for t in (src.tables or [])}
        table_names |= {t.lower() for t in (src.pii or {})}
        table_names |= {t.lower() for t in (aa.get("tables") or {})}
        table_names |= {t.lower() for t in (src.row_filters or {})}
        table_names |= {
            key.partition(".")[0].lower() for key in (aa.get("columns") or {})
        }

        pii_by_table: dict[str, set[str]] = {}
        for tbl, cols in (src.pii or {}).items():
            pii_by_table.setdefault(tbl.lower(), set()).update(c.lower() for c in cols)

        col_overrides: dict[str, dict[str, bool]] = {}
        for key, val in (aa.get("columns") or {}).items():
            tbl, _, col = key.partition(".")
            col_overrides.setdefault(tbl.lower(), {})[col.lower()] = bool(val)

        table_access = {t.lower(): bool(v) for t, v in (aa.get("tables") or {}).items()}
        row_filters = {t.lower(): str(p) for t, p in (src.row_filters or {}).items()}

        tables: dict = {}
        for tbl in sorted(table_names):
            tables[tbl] = {
                "table_access": table_access.get(tbl),
                "pii": sorted(pii_by_table.get(tbl, set())),
                "columns": dict(sorted(col_overrides.get(tbl, {}).items())),
                "row_filter": row_filters.get(tbl),
            }
        # Source type + location (path, or the non-secret connection dict) are
        # part of the surface: repointing a source at a different database swaps
        # the whole dataset behind a governed name. max_rows caps connector
        # extraction — raising it exposes more rows.
        location = src.path or (dict(sorted(src.connection.items())) if src.connection else None)
        sources[src.name] = {
            "type": src.type.value,
            "location": location,
            "max_rows": src.max_rows,
            "source_access": aa.get("source"),
            "tables": tables,
        }

    policies = {rel: _policy_dict(pol) for rel, pol in sorted(charter.policies.items())}
    # local_access governs snapshot/upload relations; normalize the same way.
    local = charter.local_access or {}
    local_norm = {
        "source": local.get("source"),
        "tables": {t.lower(): bool(v) for t, v in (local.get("tables") or {}).items()},
        "columns": {k.lower(): bool(v) for k, v in (local.get("columns") or {}).items()},
    }
    return {
        "sources": dict(sorted(sources.items())),
        "policies": policies,
        "local_access": local_norm,
    }


def surface_hash(surface: dict) -> str:
    """SHA-256 over the canonical surface JSON (order-independent)."""
    blob = json.dumps(surface, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


# --- diff -------------------------------------------------------------------
# Exposure polarity: for access toggles, True = agent sees real values (exposed),
# False = masked (protected), None = default (PII masked, rest real). Moving
# toward exposure is WIDENED; toward protection is NARROWED.
_RANK = {False: 1, None: 0, True: -1}


def _access_change(old, new, path: str, noun: str) -> Change | None:
    if old == new:
        return None
    delta = _RANK[new] - _RANK[old]
    kind = WIDENED if delta < 0 else NARROWED
    return Change(kind, path, f"{noun}: {_access_word(old)} → {_access_word(new)}")


def _access_word(v) -> str:
    return {True: "agent sees real values", False: "masked", None: "default"}[v]


def diff_surfaces(old: dict, new: dict) -> list[Change]:
    """Classify every difference between two effective surfaces."""
    changes: list[Change] = []
    _diff_sources(old.get("sources", {}), new.get("sources", {}), changes)
    _diff_local(old.get("local_access", {}), new.get("local_access", {}), changes)
    _diff_policies(old.get("policies", {}), new.get("policies", {}), changes)
    # Worst first: WIDENED, then NARROWED, then NEUTRAL; stable within a kind.
    order = {WIDENED: 0, NARROWED: 1, NEUTRAL: 2}
    changes.sort(key=lambda c: order[c.kind])
    return changes


def _diff_sources(old: dict, new: dict, out: list[Change]) -> None:
    for name in sorted(set(old) | set(new)):
        o, n = old.get(name), new.get(name)
        if o is None:
            out.append(Change(WIDENED, name, f"source '{name}' added — agent can now query it"))
            _diff_tables(name, {}, n["tables"], n.get("type"), out)
            continue
        if n is None:
            out.append(Change(NARROWED, name, f"source '{name}' removed"))
            continue
        _diff_source_meta(name, o, n, out)
        c = _access_change(o["source_access"], n["source_access"], name, f"source '{name}'")
        if c:
            out.append(c)
        _diff_tables(name, o["tables"], n["tables"], n.get("type"), out)


def _diff_source_meta(name: str, o: dict, n: dict, out: list[Change]) -> None:
    if o.get("type") != n.get("type"):
        out.append(Change(WIDENED, name,
                          f"source '{name}' type changed {o.get('type')} → {n.get('type')}"))
    if o.get("location") != n.get("location"):
        # Repointing at a different database/file swaps the dataset — fail closed.
        out.append(Change(WIDENED, name, f"source '{name}' repointed to a different location"))
    om, nm = o.get("max_rows"), n.get("max_rows")
    if om != nm:
        widened = nm is None or (om is not None and nm > om)
        kind = WIDENED if widened else NARROWED
        out.append(Change(kind, name, f"source '{name}' max_rows {om} → {nm}"))


def _table_protected(t: dict) -> bool:
    """Does this table carry any masking/filter/deny that removal would lift?"""
    return bool(
        t.get("pii") or t.get("row_filter")
        or t.get("table_access") is False
        or any(v is False for v in (t.get("columns") or {}).values())
    )


# Source types whose tables stay queryable even when un-declared: the engine
# ATTACHes the whole database, so dropping a table from the charter removes its
# governance, not its reachability.
def _is_attach_type(source_type) -> bool:
    from datacharter.models import ATTACH_TYPES, SourceType

    try:
        return SourceType(source_type) in ATTACH_TYPES
    except ValueError:
        return False


def _diff_tables(src: str, old: dict, new: dict, source_type, out: list[Change]) -> None:
    for tbl in sorted(set(old) | set(new)):
        path = f"{src}.{tbl}"
        o, n = old.get(tbl), new.get(tbl)
        if o is None:
            out.append(Change(WIDENED, path, f"table '{path}' added to the governed surface"))
            o = {"table_access": None, "pii": [], "columns": {}, "row_filter": None}
        if n is None:
            # On an ATTACH source the table stays queryable after its governance
            # is removed — so lifting masking/filters/deny is a WIDENING, not a
            # narrowing. Fail closed for that case.
            if _is_attach_type(source_type) and _table_protected(o):
                out.append(Change(
                    WIDENED, path,
                    f"table '{path}' un-declared but still queryable — its masking/"
                    f"filters no longer apply",
                ))
            else:
                out.append(Change(NARROWED, path, f"table '{path}' removed from the surface"))
            continue
        c = _access_change(o["table_access"], n["table_access"], path, f"table '{path}'")
        if c:
            out.append(c)
        _diff_pii(path, set(o["pii"]), set(n["pii"]), out)
        _diff_cols(path, o["columns"], n["columns"], out)
        _diff_row_filter(path, o["row_filter"], n["row_filter"], out)


def _diff_pii(path: str, old: set, new: set, out: list[Change]) -> None:
    for col in sorted(new - old):  # newly declared PII = now masked = protection
        out.append(Change(NARROWED, f"{path}.{col}", f"'{col}' declared PII — now masked"))
    for col in sorted(old - new):  # PII declaration removed = column unmasked
        out.append(Change(WIDENED, f"{path}.{col}", f"'{col}' no longer declared PII — unmasked"))


def _diff_cols(path: str, old: dict, new: dict, out: list[Change]) -> None:
    for col in sorted(set(old) | set(new)):
        o, n = old.get(col), new.get(col)
        c = _access_change(o, n, f"{path}.{col}", f"column '{col}'")
        if c:
            out.append(c)


def _diff_row_filter(path: str, old, new, out: list[Change]) -> None:
    if old == new:
        return
    if old is None:
        out.append(Change(NARROWED, path, f"row filter added: {new!r}"))
    elif new is None:
        out.append(Change(WIDENED, path, f"row filter removed (was {old!r})"))
    else:
        # A changed predicate could widen or narrow — cannot prove; fail closed.
        out.append(Change(WIDENED, path, f"row filter changed: {old!r} → {new!r}"))


def _diff_local(old: dict, new: dict, out: list[Change]) -> None:
    o = old or {"source": None, "tables": {}, "columns": {}}
    n = new or {"source": None, "tables": {}, "columns": {}}
    c = _access_change(o.get("source"), n.get("source"), "local", "local snapshots")
    if c:
        out.append(c)
    _diff_cols("local", o.get("tables", {}), n.get("tables", {}), out)
    _diff_cols("local", o.get("columns", {}), n.get("columns", {}), out)


_POLICY_LABELS = {
    "aggregate_only": "aggregates only",
    "no_joins": "no joins",
}


def _diff_policies(old: dict, new: dict, out: list[Change]) -> None:
    for rel in sorted(set(old) | set(new)):
        o, n = old.get(rel), new.get(rel)
        if o is None:
            out.append(Change(NARROWED, rel, f"policy added on '{rel}'"))
            o = {"aggregate_only": False, "min_group_size": None, "no_joins": False,
                 "no_joins_to": []}
        if n is None:
            out.append(Change(WIDENED, rel, f"policy removed from '{rel}' — restrictions lifted"))
            continue
        for key in ("aggregate_only", "no_joins"):
            if o[key] != n[key]:
                label = _POLICY_LABELS[key]
                if n[key]:
                    out.append(Change(NARROWED, rel, f"'{rel}': '{label}' now enforced"))
                else:
                    out.append(Change(WIDENED, rel, f"'{rel}': '{label}' no longer enforced"))
        _diff_min_group(rel, o["min_group_size"], n["min_group_size"], out)
        _diff_no_joins_to(rel, set(o["no_joins_to"]), set(n["no_joins_to"]), out)


def _diff_min_group(rel: str, old, new, out: list[Change]) -> None:
    if old == new:
        return
    if old is None:
        out.append(Change(NARROWED, rel, f"'{rel}': min group size set to {new}"))
    elif new is None:
        out.append(Change(WIDENED, rel, f"'{rel}': min group size removed (was {old})"))
    elif new < old:
        out.append(Change(WIDENED, rel, f"'{rel}': min group size lowered {old} → {new}"))
    else:
        out.append(Change(NARROWED, rel, f"'{rel}': min group size raised {old} → {new}"))


def _diff_no_joins_to(rel: str, old: set, new: set, out: list[Change]) -> None:
    for r in sorted(new - old):
        out.append(Change(NARROWED, rel, f"'{rel}': join to '{r}' now blocked"))
    for r in sorted(old - new):
        out.append(Change(WIDENED, rel, f"'{rel}': join to '{r}' no longer blocked"))


def render_changes(changes: list[Change]) -> str:
    """Human-readable text report, grouped worst-first."""
    if not changes:
        return "No change to the agent-visible access surface."
    icons = {WIDENED: "⚠️ ", NARROWED: "🔒", NEUTRAL: "• "}
    lines: list[str] = []
    widened = sum(1 for c in changes if c.kind == WIDENED)
    narrowed = sum(1 for c in changes if c.kind == NARROWED)
    lines.append(f"Access surface changes: {widened} widened, {narrowed} narrowed.")
    for c in changes:
        lines.append(f"  {icons[c.kind]} {c.kind:<8} {c.detail}")
    return "\n".join(lines)
