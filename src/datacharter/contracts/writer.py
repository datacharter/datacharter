"""Round-trip charter.yaml editing that preserves comments and ordering."""

from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML

from datacharter.contracts.loader import CHARTER_FILE

__all__ = ["upsert_source", "remove_source", "set_pii", "ContractWriteError"]


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


def set_pii(workspace: Path, source: str, table: str, columns: list[str]) -> None:
    """Merge PII column names into one source's pii map (round-trip).

    Touches only the `pii` field, so credential references and every other part
    of the source entry are preserved verbatim (never resurfaces a secret).
    """
    path = workspace / CHARTER_FILE
    y, data = _load(path)
    sources = data.get("sources") or {}
    if source not in sources:
        raise ContractWriteError(f"Source '{source}' is not in the charter.")
    entry = sources[source]
    pii = entry.get("pii")
    if pii is None:
        pii = {}
        entry["pii"] = pii
    existing = list(pii.get(table) or [])
    pii[table] = existing + [c for c in columns if c not in existing]
    _write(path, y, data)
