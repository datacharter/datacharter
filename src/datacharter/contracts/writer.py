"""Round-trip charter.yaml editing that preserves comments and ordering."""

from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML

from datacharter.contracts.loader import CHARTER_FILE

__all__ = [
    "upsert_source",
    "remove_source",
    "set_pii",
    "replace_pii",
    "set_row_filter",
    "set_policy_sentences",
    "ContractWriteError",
]


class ContractWriteError(Exception):
    """Refused a contract write (e.g. a credential literal)."""


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _load(path: Path):
    y = _yaml()
    data = y.load(path.read_text()) if path.exists() else None
    data = data or {}
    data.setdefault("version", 1)
    if not data.get("sources"):
        data["sources"] = {}
    return y, data


def _write(path: Path, y: YAML, data) -> None:
    buf = io.StringIO()
    y.dump(data, buf)
    path.write_text(buf.getvalue())


def _reject_literal_credentials(body: dict) -> None:
    for key, value in (body.get("credentials") or {}).items():
        if not (isinstance(value, str) and value.startswith("${") and value.endswith("}")):
            raise ContractWriteError(
                f"credentials.{key} must be a ${{NAME}} reference, never a literal."
            )


def upsert_source(workspace: Path, name: str, body: dict) -> None:
    _reject_literal_credentials(body)
    path = workspace / CHARTER_FILE
    y, data = _load(path)
    # Governance survives an edit (F-6): the source form carries connection
    # shape only — replacing the body wholesale silently stripped masking
    # overrides, row-level security, and table context on any hostname change.
    existing = (data.get("sources") or {}).get(name) or {}
    for key in ("agent_access", "row_filters", "context", "pii"):
        if key in existing and key not in body:
            body[key] = existing[key]
    data["sources"][name] = body
    _write(path, y, data)


def remove_source(workspace: Path, name: str) -> None:
    path = workspace / CHARTER_FILE
    if not path.exists():
        return
    y, data = _load(path)
    data["sources"].pop(name, None)
    _write(path, y, data)


def set_agent_access(
    workspace: Path, source: str, table: str | None, column: str | None, value: bool
) -> None:
    """Persist one agent-access override (on=real, off=masked) at field/table/source level.

    Touches only the source's `agent_access` block; everything else is preserved verbatim."""
    path = workspace / CHARTER_FILE
    y, data = _load(path)
    if source == "local":
        # `local.*` snapshots have no source entry — overrides live top-level.
        aa = data.get("local_access")
        if aa is None:
            aa = {}
            data["local_access"] = aa
    else:
        sources = data.get("sources") or {}
        if source not in sources:
            raise ContractWriteError(f"Source '{source}' is not in the charter.")
        entry = sources[source]
        aa = entry.get("agent_access")
        if aa is None:
            aa = {}
            entry["agent_access"] = aa
    # A coarser toggle clears the finer overrides beneath it — otherwise a
    # stale field override silently wins over a later table/source click and
    # the toggle looks broken (worse: a table masked "everything" can leave
    # one previously-unmasked PII column visible).
    if column is not None and table is not None:
        aa.setdefault("columns", {})[f"{table}.{column}"] = value
    elif table is not None:
        cols = aa.get("columns") or {}
        for key in [k for k in cols if k.startswith(f"{table}.")]:
            del cols[key]
        aa.setdefault("tables", {})[table] = value
    else:
        aa.pop("columns", None)
        aa.pop("tables", None)
        aa["source"] = value
    _write(path, y, data)


def _source_entry(data, source: str):
    sources = data.get("sources") or {}
    if source not in sources:
        raise ContractWriteError(f"Source '{source}' is not in the charter.")
    return sources[source]


def set_pii(workspace: Path, source: str, table: str, columns: list[str]) -> None:
    """Merge PII column names into one source's pii map (round-trip).

    Touches only the `pii` field, so credential references and every other part
    of the source entry are preserved verbatim (never resurfaces a secret).
    """
    path = workspace / CHARTER_FILE
    y, data = _load(path)
    entry = _source_entry(data, source)
    pii = entry.get("pii")
    if pii is None:
        pii = {}
        entry["pii"] = pii
    existing = list(pii.get(table) or [])
    pii[table] = existing + [c for c in columns if c not in existing]
    _write(path, y, data)


def replace_pii(workspace: Path, source: str, table: str, columns: list[str]) -> None:
    """Replace one table's PII list. Empty columns drops that table from the map."""
    path = workspace / CHARTER_FILE
    y, data = _load(path)
    entry = _source_entry(data, source)
    pii = entry.get("pii")
    if pii is None:
        pii = {}
        entry["pii"] = pii
    unique = list(dict.fromkeys(columns))
    if unique:
        pii[table] = unique
    else:
        pii.pop(table, None)
        if not pii:
            entry.pop("pii", None)
    _write(path, y, data)


def _validate_predicate(predicate: str) -> None:
    import json

    import duckdb

    con = duckdb.connect()
    try:
        raw = con.execute(
            "SELECT json_serialize_sql(?)", [f"SELECT 1 WHERE ({predicate})"]
        ).fetchone()[0]
        tree = json.loads(raw)
        if isinstance(tree, dict) and tree.get("error"):
            msg = tree.get("error_message") or tree.get("error")
            raise ContractWriteError(f"Invalid row filter: {msg}")
    except ContractWriteError:
        raise
    except Exception as exc:
        raise ContractWriteError(f"Invalid row filter: {exc}") from None
    finally:
        con.close()


def set_row_filter(workspace: Path, source: str, table: str, predicate: str) -> None:
    """Set or clear one table's row filter. Empty predicate removes it."""
    pred = (predicate or "").strip()
    if pred:
        _validate_predicate(pred)
    path = workspace / CHARTER_FILE
    y, data = _load(path)
    entry = _source_entry(data, source)
    filters = entry.get("row_filters")
    if filters is None:
        filters = {}
        entry["row_filters"] = filters
    if pred:
        filters[table] = pred
    else:
        filters.pop(table, None)
        if not filters:
            entry.pop("row_filters", None)
    _write(path, y, data)


def set_policy_sentences(workspace: Path, relation: str, sentences: list[str]) -> None:
    """Replace one relation's policy sentences. Empty list removes the relation."""
    from datacharter.contracts.loader_errors import CharterError
    from datacharter.contracts.policies import parse_policies

    cleaned = [s.strip() for s in sentences if isinstance(s, str) and s.strip()]
    if cleaned:
        try:
            parse_policies({relation: cleaned})
        except CharterError as exc:
            raise ContractWriteError(str(exc)) from None
    path = workspace / CHARTER_FILE
    y, data = _load(path)
    policies = data.get("policies")
    if policies is None:
        policies = {}
        data["policies"] = policies
    if cleaned:
        policies[relation] = cleaned
    else:
        policies.pop(relation, None)
        if not policies:
            data.pop("policies", None)
    _write(path, y, data)
