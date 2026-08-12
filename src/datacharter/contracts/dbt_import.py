"""Generate a `charter.yaml` scaffold from a dbt project's `manifest.json`.

Turns any dbt project into a governed DataCharter contract in one command: the
warehouse type comes from the dbt adapter, models + sources become tables grouped
by (database, schema), columns flagged PII (via `meta`/`tags`) become masked
columns, and model/source descriptions become per-table agent context. Connection
host/credentials aren't in the manifest, so they're emitted as `${ENV}`
placeholders for you to fill.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

# dbt adapter (metadata.adapter_type) -> DataCharter source type.
_ADAPTER_TO_TYPE = {
    "snowflake": "snowflake",
    "postgres": "postgres",
    "redshift": "postgres",  # Redshift speaks the Postgres wire protocol
    "bigquery": "bigquery",
    "duckdb": "duckdb",
    "mysql": "mysql",
    "sqlserver": "mssql",
    "synapse": "mssql",
    "fabric": "mssql",
}

# Column tags / meta keys that mark a column as PII (→ masked from agents).
_PII_TAGS = {"pii", "sensitive", "phi", "personal", "gdpr", "confidential"}
_PII_META_KEYS = ("pii", "contains_pii", "sensitive", "is_pii", "policy_tags")


def _is_pii(col: dict) -> bool:
    meta = col.get("meta") or {}
    if any(meta.get(k) for k in _PII_META_KEYS):
        return True
    tags = [str(t).lower() for t in (col.get("tags") or [])]
    return any(t in _PII_TAGS for t in tags)


def _sanitize_name(raw: str) -> str:
    """A valid charter source name (`^[a-z][a-z0-9_]{0,62}$`) from a dbt db/schema."""
    slug = re.sub(r"[^a-z0-9_]", "_", (raw or "").lower()).strip("_")
    if not slug:
        return "source"
    if not slug[0].isalpha():
        slug = "src_" + slug
    return slug[:63].rstrip("_") or "source"


def _nodes(manifest: dict) -> list[dict]:
    """Models + seeds (from `nodes`) and raw sources (from `sources`)."""
    out = [
        n for n in (manifest.get("nodes") or {}).values()
        if n.get("resource_type") in ("model", "seed")
    ]
    out += list((manifest.get("sources") or {}).values())
    return out


def _connection(source_type: str, database: str, schema: str) -> tuple[dict, dict]:
    """(connection, credentials) scaffold for a warehouse type — real db/schema from
    the manifest, `${ENV}` placeholders for what the manifest can't know."""
    if source_type == "snowflake":
        conn = {"account": "${SNOWFLAKE_ACCOUNT}", "database": database,
                "schema": schema, "warehouse": "${SNOWFLAKE_WAREHOUSE}",
                "user": "${SNOWFLAKE_USER}"}
        return conn, {"password": "${SNOWFLAKE_PASSWORD}"}
    if source_type == "bigquery":
        return {"project": database or "${GCP_PROJECT}", "dataset": schema}, {}
    if source_type == "duckdb":
        return {"database": database or "warehouse.duckdb"}, {}
    conn = {"host": "${DB_HOST}", "database": database, "user": "${DB_USER}"}
    if schema:
        conn["schema"] = schema
    return conn, {"password": "${DB_PASSWORD}"}


def build_charter(manifest: dict) -> tuple[dict, dict]:
    """Return (charter-dict, summary). Groups nodes by (database, schema) into sources."""
    adapter = (manifest.get("metadata") or {}).get("adapter_type", "")
    source_type = _ADAPTER_TO_TYPE.get(adapter, adapter or "postgres")

    groups: dict[tuple[str, str], dict] = {}
    for node in _nodes(manifest):
        db = node.get("database") or ""
        schema = node.get("schema") or ""
        table = node.get("identifier") or node.get("alias") or node.get("name")
        if not table:
            continue
        g = groups.setdefault((db, schema), {"tables": [], "pii": {}, "context": {}})
        if table not in g["tables"]:
            g["tables"].append(table)
        pii_cols = [c for c, cdef in (node.get("columns") or {}).items() if _is_pii(cdef)]
        if pii_cols:
            g["pii"][table] = sorted(pii_cols)
        desc = (node.get("description") or "").strip()
        if desc:
            g["context"][table] = desc

    sources: dict[str, dict] = {}
    used: set[str] = set()
    for (db, schema), g in sorted(groups.items()):
        base = _sanitize_name(schema or db)
        name = base
        if name in used:  # disambiguate a schema reused across databases
            name = _sanitize_name(f"{db}_{schema}")
        used.add(name)
        conn, creds = _connection(source_type, db, schema)
        src: dict = {"type": source_type, "connection": conn}
        if creds:
            src["credentials"] = creds
        src["tables"] = sorted(g["tables"])
        if g["pii"]:
            src["pii"] = dict(sorted(g["pii"].items()))
        if g["context"]:
            src["context"] = dict(sorted(g["context"].items()))
        sources[name] = src

    charter = {"version": 1, "sources": sources}
    summary = {
        "adapter": adapter,
        "source_type": source_type,
        "sources": len(sources),
        "tables": sum(len(s["tables"]) for s in sources.values()),
        "pii_columns": sum(
            len(cols) for s in sources.values() for cols in s.get("pii", {}).values()
        ),
        "unmapped_adapter": adapter not in _ADAPTER_TO_TYPE and bool(adapter),
    }
    return charter, summary


def render(charter: dict) -> str:
    """Charter dict → YAML text with a guiding header."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(charter, buf)
    header = (
        "# Generated by `datacharter import dbt`. Review, then:\n"
        "#   1. fill each source's connection host/account + ${ENV} credentials\n"
        "#   2. `datacharter scan`   — confirm / extend the PII detection\n"
        "#   3. `datacharter serve`  — explore the governed workspace\n\n"
    )
    return header + buf.getvalue()


def import_manifest(manifest_path: str) -> tuple[str, dict]:
    """Read a dbt manifest.json and return (charter-yaml-text, summary)."""
    manifest = json.loads(Path(manifest_path).read_text())
    charter, summary = build_charter(manifest)
    return render(charter), summary
