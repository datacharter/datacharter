"""Interop with the Open Data Contract Standard (ODCS, bitol.io).

`charter.yaml` is a data contract; ODCS is the open standard for one. This maps
between them so DataCharter plugs into the data-contract ecosystem:

- `import_odcs` turns an ODCS `DataContract` into a governed charter — the source
  type/connection from `servers`, tables + PII from `schema.properties`.
- `export_odcs` publishes a charter as an ODCS `DataContract` — each source a
  server, each table a schema object, each declared-PII column classified `PII`.

The mapping is intentionally lossless where the two overlap and explicit where they
don't (credentials become `${ENV}` placeholders; a charter lists only PII columns,
so a static export marks those and leaves the full column list to the source).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from datacharter.contracts.dbt_import import _sanitize_name

__all__ = ["import_odcs", "export_odcs", "import_odcs_file", "export_odcs_yaml"]

_ODCS_TYPE_TO_SOURCE = {
    "postgres": "postgres", "postgresql": "postgres", "mysql": "mysql",
    "snowflake": "snowflake", "bigquery": "bigquery", "sqlserver": "mssql",
    "mssql": "mssql", "duckdb": "duckdb", "sqlite": "sqlite", "databricks": "iceberg_rest",
}
_SOURCE_TO_ODCS_TYPE = {"postgres": "postgres", "mysql": "mysql", "snowflake": "snowflake",
                        "bigquery": "bigquery", "mssql": "sqlserver", "duckdb": "duckdb",
                        "sqlite": "sqlite", "iceberg_rest": "databricks"}

_PII_CLASSIFICATIONS = {"pii", "personal", "sensitive", "restricted", "confidential"}
_PII_TAGS = {"pii", "personal", "sensitive", "phi", "gdpr"}


def _prop_is_pii(prop: dict) -> bool:
    if str(prop.get("classification", "")).lower() in _PII_CLASSIFICATIONS:
        return True
    tags = [str(t).lower() for t in (prop.get("tags") or [])]
    return any(t in _PII_TAGS for t in tags)


def _odcs_connection(source_type: str, server: dict) -> tuple[dict, dict]:
    """(connection, credentials) from an ODCS server, `${ENV}` where it can't say."""
    db = server.get("database") or ""
    schema = server.get("schema") or ""
    if source_type == "snowflake":
        conn = {"account": server.get("account") or "${SNOWFLAKE_ACCOUNT}", "database": db,
                "schema": schema or "PUBLIC", "warehouse": server.get("warehouse") or
                "${SNOWFLAKE_WAREHOUSE}", "user": "${SNOWFLAKE_USER}"}
        return conn, {"password": "${SNOWFLAKE_PASSWORD}"}
    if source_type == "bigquery":
        return {"project": server.get("project") or db or "${GCP_PROJECT}",
                "dataset": server.get("dataset") or schema}, {}
    if source_type == "duckdb":
        return {"database": db or "warehouse.duckdb"}, {}
    conn = {"host": server.get("host") or "${DB_HOST}", "database": db, "user": "${DB_USER}"}
    if schema:
        conn["schema"] = schema
    return conn, {"password": "${DB_PASSWORD}"}


def import_odcs(doc: dict) -> tuple[dict, dict]:
    """ODCS DataContract dict → (charter-dict, summary)."""
    servers = doc.get("servers") or []
    server = servers[0] if servers else {}
    stype = _ODCS_TYPE_TO_SOURCE.get(str(server.get("type", "")).lower(), "postgres")
    name = _sanitize_name(doc.get("name") or server.get("server") or str(doc.get("id") or "source"))
    conn, creds = _odcs_connection(stype, server)

    tables: list[str] = []
    pii: dict[str, list[str]] = {}
    context: dict[str, str] = {}
    for tbl in (doc.get("schema") or []):
        tname = tbl.get("name") or tbl.get("physicalName")
        if not tname:
            continue
        if tname not in tables:
            tables.append(tname)
        pii_cols = [p["name"] for p in (tbl.get("properties") or [])
                    if p.get("name") and _prop_is_pii(p)]
        if pii_cols:
            pii[tname] = sorted(pii_cols)
        desc = (tbl.get("description") or "").strip()
        if desc:
            context[tname] = desc

    src: dict = {"type": stype, "connection": conn}
    if creds:
        src["credentials"] = creds
    src["tables"] = sorted(tables)
    if pii:
        src["pii"] = dict(sorted(pii.items()))
    if context:
        src["context"] = dict(sorted(context.items()))
    charter = {"version": 1, "sources": {name: src}}
    summary = {
        "source_type": stype, "source": name, "tables": len(tables),
        "pii_columns": sum(len(c) for c in pii.values()),
        "unmapped_type": str(server.get("type", "")).lower() not in _ODCS_TYPE_TO_SOURCE
        and bool(server.get("type")),
    }
    return charter, summary


def export_odcs(charter: Any) -> dict:
    """A loaded `Charter` → ODCS DataContract dict. Marks declared-PII columns
    `classification: PII`; a static export lists tables, not full column sets."""
    servers, schema = [], []
    for src in charter.sources:
        odcs_type = _SOURCE_TO_ODCS_TYPE.get(src.type.value, src.type.value)
        entry = {"server": src.name, "type": odcs_type}
        for key in ("host", "database", "schema", "project", "dataset", "account", "warehouse"):
            if src.connection.get(key):
                entry[key] = src.connection[key]
        servers.append(entry)
        for table in src.tables:
            props = [{"name": col, "logicalType": "string", "classification": "PII"}
                     for col in sorted(src.pii.get(table, []))]
            schema.append({
                "name": table, "physicalName": f"{src.name}.{table}",
                "logicalType": "object", "properties": props,
            })
    return {
        "apiVersion": "v3.0.0", "kind": "DataContract",
        "id": _sanitize_name(getattr(charter, "name", "") or "datacharter-export"),
        "name": "datacharter-export", "version": "1.0.0", "status": "active",
        "servers": servers, "schema": schema,
    }


def _render_charter(charter: dict) -> str:
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(charter, buf)
    header = (
        "# Generated by `datacharter import odcs`. Review, then:\n"
        "#   1. fill each source's connection + ${ENV} credentials\n"
        "#   2. `datacharter scan`   — confirm / extend the PII detection\n"
        "#   3. `datacharter serve`  — explore the governed workspace\n\n"
    )
    return header + buf.getvalue()


def import_odcs_file(path: str) -> tuple[str, dict]:
    """Read an ODCS contract (YAML or JSON) and return (charter-yaml-text, summary)."""
    text = Path(path).read_text()
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        from ruamel.yaml import YAML
        doc = YAML(typ="safe").load(text)
    charter, summary = import_odcs(doc)
    return _render_charter(charter), summary


def export_odcs_yaml(charter: Any) -> str:
    """A loaded Charter → ODCS DataContract YAML text."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(export_odcs(charter), buf)
    return buf.getvalue()
