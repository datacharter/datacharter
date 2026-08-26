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
    SourceType.EXCEL: "read_xlsx",
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


def _motherduck_registration(source: Source) -> list[str]:
    """MotherDuck = DuckDB-in-the-cloud, attached via the signed `motherduck`
    extension and the `md:` scheme. The token is set with `SET motherduck_token`
    (kept out of the ATTACH string) — a token is required so the extension never
    falls back to the interactive browser SSO flow, which would hang a server. The
    surface is attached READ_ONLY."""
    token = source.credentials.get("token") or source.connection.get("token")
    if not token:
        raise SourceConfigError(
            f"Source '{source.name}' (motherduck) needs a token — set "
            "credentials.token: ${MOTHERDUCK_TOKEN}."
        )
    database = str(source.connection.get("database", "")).strip()
    target = f"md:{database}" if database else "md:"
    return [
        "INSTALL motherduck",
        "LOAD motherduck",
        f"SET motherduck_token = {_q(token)}",
        f"ATTACH {_q(target)} AS {source.name} (TYPE motherduck, READ_ONLY)",
    ]


def _iceberg_rest_registration(source: Source) -> list[str]:
    """An Iceberg REST catalog (Polaris / Nessie / Lakekeeper / Unity / Glue /
    S3 Tables), attached read-only via the core `iceberg` extension. Auth rides a
    DuckDB secret (a static `token`, an OAuth2 `client_id`/`client_secret`, or AWS
    keys for Glue/S3 Tables) — never the ATTACH string."""
    conn, creds = source.connection, source.credentials
    warehouse = str(conn.get("warehouse", "")).strip()
    endpoint = conn.get("endpoint")
    endpoint_type = conn.get("endpoint_type")
    if not warehouse:
        raise SourceConfigError(
            f"Source '{source.name}' (iceberg_rest) needs connection.warehouse."
        )
    if not endpoint and not endpoint_type:
        raise SourceConfigError(
            f"Source '{source.name}' (iceberg_rest) needs connection.endpoint "
            "(or connection.endpoint_type GLUE/S3_TABLES)."
        )
    secret_params: list[str] = []
    for key, kw in (("token", "TOKEN"), ("client_id", "CLIENT_ID"),
                    ("client_secret", "CLIENT_SECRET"), ("key_id", "KEY_ID"),
                    ("secret", "SECRET"), ("region", "REGION")):
        if creds.get(key):
            secret_params.append(f"{kw} {_q(creds[key])}")
    if conn.get("oauth2_server_uri"):
        secret_params.append(f"OAUTH2_SERVER_URI {_q(conn['oauth2_server_uri'])}")

    stmts = ["INSTALL iceberg", "LOAD iceberg"]
    if secret_params:
        stmts.append(
            f"CREATE OR REPLACE TEMPORARY SECRET {source.name}_ice "
            f"(TYPE iceberg, {', '.join(secret_params)})"
        )
    opts = ["TYPE iceberg"]
    if endpoint:
        opts.append(f"ENDPOINT {_q(endpoint)}")
    if endpoint_type:
        opts.append(f"ENDPOINT_TYPE {_q(endpoint_type)}")
    # DuckDB defaults to oauth2 and rejects an unauthenticated attach; a dev/local
    # catalog needs an explicit authorization_type: none.
    if conn.get("authorization_type"):
        opts.append(f"AUTHORIZATION_TYPE {_q(conn['authorization_type'])}")
    opts.append("READ_ONLY")
    stmts.append(f"ATTACH {_q(warehouse)} AS {source.name} ({', '.join(opts)})")
    return stmts


#: DuckLake catalog backends whose DuckDB extension must be present to read the
#: metadata database. The scheme prefix identifies each in `connection.metadata`.
_DUCKLAKE_CATALOG_EXT = {"postgres:": "postgres", "mysql:": "mysql", "sqlite:": "sqlite"}
_REMOTE_SCHEMES = ("s3://", "gcs://", "gs://", "az://", "azure://", "r2://")


def _ducklake_registration(source: Source, workspace: Path) -> list[str]:
    """A DuckLake lakehouse catalog — metadata in a DuckDB file or a
    SQLite/Postgres/MySQL database, data as Parquet on the local filesystem or
    object storage — attached read-only via the `ducklake` extension. The catalog
    stores its own DATA_PATH, so it is only needed on first attach or to override.
    Object-store data rides a DuckDB secret; catalog-DB credentials go in the
    `metadata` connection string as `${ENV}` references (the DuckLake convention)."""
    conn = source.connection
    metadata = str(conn.get("metadata") or "").strip()
    if not metadata:
        raise SourceConfigError(
            f"Source '{source.name}' (ducklake) needs connection.metadata — a catalog "
            "file path, or a 'postgres:' / 'sqlite:' / 'mysql:' connection string."
        )
    stmts = ["INSTALL ducklake", "LOAD ducklake"]
    # A SQL-catalog scheme passes through as-is (and needs its backend extension);
    # a bare local path is resolved against the workspace like other file sources.
    backend = next((e for p, e in _DUCKLAKE_CATALOG_EXT.items() if metadata.startswith(p)), None)
    if backend:
        stmts += [f"INSTALL {backend}", f"LOAD {backend}"]
    elif "://" not in metadata:
        metadata = str((workspace / metadata).resolve())

    data_path = str(conn.get("data_path") or "").strip()
    if data_path.startswith(_REMOTE_SCHEMES):
        secret = _s3_secret(source)
        if secret:
            stmts.append(secret)
    opts = []
    if data_path:
        opts.append(f"DATA_PATH {_q(data_path)}")
    if conn.get("metadata_schema"):
        opts.append(f"METADATA_SCHEMA {_q(conn['metadata_schema'])}")
    opts.append("READ_ONLY")
    stmts.append(f"ATTACH {_q('ducklake:' + metadata)} AS {source.name} ({', '.join(opts)})")
    return stmts


def registration_sql(source: Source, workspace: Path) -> list[str]:
    """Statements that register a source on a session (secrets + attach/view)."""
    if source.type == SourceType.MOTHERDUCK:
        return _motherduck_registration(source)
    if source.type == SourceType.ICEBERG_REST:
        return _iceberg_rest_registration(source)
    if source.type == SourceType.DUCKLAKE:
        return _ducklake_registration(source, workspace)
    if source.type == SourceType.SQLITE:
        path = _resolve_path(source, workspace)
        return [f"ATTACH {_q(path)} AS {source.name} (TYPE sqlite, READ_ONLY)"]
    if source.type == SourceType.DUCKDB:
        path = _resolve_path(source, workspace)
        return [f"ATTACH {_q(path)} AS {source.name} (READ_ONLY)"]
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
    if st in (SourceType.SQLITE, SourceType.DUCKDB):
        return f"{name}.main.{table}"
    if st == SourceType.MOTHERDUCK:
        return f"{name}.{conn.get('schema', 'main')}.{table}"
    if st == SourceType.ICEBERG_REST:  # Iceberg namespace == schema
        return f"{name}.{conn.get('namespace', 'default')}.{table}"
    if st == SourceType.DUCKLAKE:
        return f"{name}.{conn.get('schema', 'main')}.{table}"
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
