"""Per-source-type registration SQL builders + compatibility-view aliasing (D10)."""

from __future__ import annotations

from pathlib import Path

from datacharter.models import FILE_TYPES, Source, SourceType

__all__ = [
    "registration_sql",
    "compatibility_view_sql",
    "qualified_name",
    "SourceConfigError",
]


class SourceConfigError(Exception):
    """Raised when a source definition can't be turned into registration SQL."""


_FILE_READERS = {
    SourceType.CSV: "read_csv",
    SourceType.PARQUET: "read_parquet",
    SourceType.JSON: "read_json",
    SourceType.ICEBERG: "iceberg_scan",
    SourceType.DELTA: "delta_scan",
}

_DB_SECRET_KEYS = {
    SourceType.POSTGRES: {"host", "port", "database", "user", "password"},
    SourceType.MYSQL: {"host", "port", "database", "user", "password"},
    SourceType.MSSQL: {"host", "port", "database", "user", "password"},
}


def _q(value: str | int) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _ident_ok(name: str) -> bool:
    return bool(name) and all(ch.isalnum() or ch == "_" for ch in name)


def _resolve_path(source: Source, workspace: Path) -> str:
    if not source.path:
        raise SourceConfigError(f"Source '{source.name}' ({source.type}) requires a path.")
    if "://" in source.path:
        return source.path
    return str((workspace / source.path).resolve())


def _s3_secret(source: Source) -> str | None:
    creds = source.credentials
    if not creds:
        return None
    parts = [f"CREATE OR REPLACE TEMPORARY SECRET {source.name}_s3 (TYPE s3"]
    mapping = {"key_id": "KEY_ID", "secret": "SECRET", "region": "REGION", "endpoint": "ENDPOINT"}
    for key, kw in mapping.items():
        if key in creds:
            parts.append(f", {kw} {_q(creds[key])}")
    parts.append(")")
    return "".join(parts)


def _db_registration(source: Source) -> list[str]:
    merged: dict[str, str | int] = {**source.connection, **source.credentials}
    fields = {k: v for k, v in merged.items() if k in _DB_SECRET_KEYS[source.type]}
    if "database" not in fields:
        raise SourceConfigError(f"Source '{source.name}' needs connection.database.")
    secret = f"{source.name}_secret"
    kv = ", ".join(f"{k.upper()} {_q(v)}" for k, v in sorted(fields.items()))
    return [
        f"CREATE OR REPLACE TEMPORARY SECRET {secret} (TYPE {source.type.value}, {kv})",
        f"ATTACH '' AS {source.name} (TYPE {source.type.value}, SECRET {secret}, READ_ONLY)",
    ]


def _bigquery_registration(source: Source) -> list[str]:
    project = source.connection.get("project") or source.connection.get("project_id")
    if not project:
        raise SourceConfigError(f"Source '{source.name}' (bigquery) needs connection.project.")
    conn = f"project={project}"
    dataset = source.connection.get("dataset") or source.connection.get("dataset_id")
    if dataset:
        conn += f" dataset={dataset}"
    return [f"ATTACH {_q(conn)} AS {source.name} (TYPE bigquery, READ_ONLY)"]


def registration_sql(source: Source, workspace: Path) -> list[str]:
    """Statements that register a source on a session (secrets + attach/view)."""
    if source.type == SourceType.SQLITE:
        path = _resolve_path(source, workspace)
        return [f"ATTACH {_q(path)} AS {source.name} (TYPE sqlite, READ_ONLY)"]
    if source.type == SourceType.BIGQUERY:
        return _bigquery_registration(source)
    if source.type in _DB_SECRET_KEYS:
        return _db_registration(source)
    if source.type in FILE_TYPES:
        path = _resolve_path(source, workspace)
        stmts = []
        if path.startswith("s3://"):
            secret = _s3_secret(source)
            if secret:
                stmts.append(secret)
        reader = _FILE_READERS[source.type]
        stmts.append(f"CREATE OR REPLACE VIEW {source.name} AS FROM {reader}({_q(path)})")
        return stmts
    raise SourceConfigError(f"Unsupported source type: {source.type}")


def qualified_name(source: Source, table: str) -> str:
    """Fully-qualified relation for one table, per the source's ATTACH scheme (D10)."""
    if not _ident_ok(table):
        raise SourceConfigError(f"Invalid table name: {table!r}")
    st, name, conn = source.type, source.name, source.connection
    if st == SourceType.POSTGRES:
        return f"{name}.{conn.get('schema', 'public')}.{table}"
    if st == SourceType.MYSQL:
        db = conn.get("database")
        return f"{name}.{db}.{table}" if db else f"{name}.{table}"
    if st == SourceType.BIGQUERY:
        ds = conn.get("dataset") or conn.get("dataset_id")
        return f"{name}.{ds}.{table}" if ds else f"{name}.{table}"
    if st == SourceType.SQLITE:
        return f"{name}.main.{table}"
    if st == SourceType.MSSQL:
        return f"{name}.{conn.get('schema', 'dbo')}.{table}"
    return f"{name}.{table}"


def compatibility_view_sql(source: Source, tables: list[str]) -> list[str]:
    """Flat `<source>__<table>` alias views over qualified names (D10 uniform namespace)."""
    stmts = []
    for table in tables:
        if not _ident_ok(table):
            raise SourceConfigError(f"Invalid table name: {table!r}")
        alias = f"{source.name}__{table}".lower()
        qualified = qualified_name(source, table)
        stmts.append(f'CREATE OR REPLACE VIEW "{alias}" AS SELECT * FROM {qualified}')
    return stmts
