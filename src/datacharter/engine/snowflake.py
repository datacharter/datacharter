"""Snowflake connector fallback: extract (filter-pushed) into local DuckDB tables (D10)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from datacharter.engine.pushdown import Pushdown
from datacharter.models import Source

if TYPE_CHECKING:
    import duckdb

__all__ = ["materialize_snowflake", "run_snowflake_sql", "SnowflakeUnavailable"]

_EXTRACT_ROW_CAP = 1_000_000
_CHUNK = 10_000

# DuckDB type per snowflake-connector type_code (cursor.description[1]).
_TYPE_CODE_TO_DUCKDB = {
    0: "DOUBLE",  # FIXED / NUMBER
    1: "DOUBLE",  # REAL
    2: "VARCHAR",  # TEXT
    3: "DATE",
    4: "TIMESTAMP",
    5: "VARCHAR",  # VARIANT
    6: "TIMESTAMP",
    7: "TIMESTAMP",
    8: "TIMESTAMP",
    13: "BOOLEAN",
}


class SnowflakeUnavailable(Exception):
    """snowflake-connector-python is not installed."""


def _connect(source: Source):
    try:
        import snowflake.connector  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise SnowflakeUnavailable(
            "Snowflake support needs the extra: pip install 'datacharter[snowflake]'."
        ) from exc
    conn = source.connection
    creds = source.credentials
    params: dict[str, Any] = {
        "account": conn.get("account"),
        "user": conn.get("user"),
        "database": conn.get("database"),
        "schema": conn.get("schema", "PUBLIC"),
        "warehouse": conn.get("warehouse"),
    }
    if "password" in creds:
        params["password"] = creds["password"]
    if "private_key" in creds:
        params["private_key"] = creds["private_key"]
    return snowflake.connector.connect(**{k: v for k, v in params.items() if v is not None})


def _cap_for(source: Source) -> int:
    return source.max_rows or _EXTRACT_ROW_CAP


def materialize_snowflake(
    conn: duckdb.DuckDBPyConnection,
    source: Source,
    tables: list[str],
    *,
    pushdowns: dict[str, Pushdown] | None = None,
    connector_factory=None,
) -> dict[str, int | None]:
    """Pull each Snowflake table into a local `<source>__<table>` DuckDB table.

    Filter/projection come from the per-table Pushdown (computed from the query
    AST); the source's cap bounds the pull. Returns {table: cap_if_truncated} —
    the cap value when the table held more rows than the cap, else None. Result
    tables read exactly like ATTACH'd sources once the alias points at them.
    """
    pushdowns = pushdowns or {}
    cap = _cap_for(source)
    sf = (connector_factory or _connect)(source)
    truncated: dict[str, int | None] = {}
    try:
        for table in tables:
            if not table.replace("_", "").isalnum():
                raise ValueError(f"Invalid table name: {table!r}")
            alias = f"{source.name}__{table}".lower()
            # Probe one past the cap so a full result is detectable as truncation.
            extract = pushdowns.get(table, Pushdown()).select_sql(table, cap + 1)
            cur = sf.cursor()
            try:
                cur.execute(extract)
                if not cur.description:
                    truncated[table] = None
                    continue
                cols = [d[0] for d in cur.description]
                types = [_TYPE_CODE_TO_DUCKDB.get(d[1], "VARCHAR") for d in cur.description]
                col_defs = ", ".join(f'"{c}" {t}' for c, t in zip(cols, types, strict=False))
                conn.execute(f'DROP TABLE IF EXISTS "{alias}"')
                conn.execute(f'CREATE TABLE "{alias}" ({col_defs})')
                placeholders = ", ".join("?" for _ in cols)
                insert = f'INSERT INTO "{alias}" VALUES ({placeholders})'
                truncated[table] = cap if _insert_capped(conn, insert, cur, cap) else None
            finally:
                cur.close()
    finally:
        sf.close()
    return truncated


def _insert_capped(conn, insert: str, cursor, cap: int) -> bool:
    """Insert up to `cap` rows; return True if the source held more."""
    inserted = 0
    while True:
        chunk = cursor.fetchmany(_CHUNK)
        if not chunk:
            return False
        if inserted + len(chunk) > cap:
            conn.executemany(insert, chunk[: cap - inserted])
            return True
        conn.executemany(insert, chunk)
        inserted += len(chunk)


def run_snowflake_sql(
    source: Source, sql: str, fetch_cap: int, *, connector_factory=None
) -> tuple[list[tuple], bool]:
    """Run one reconstructed query on Snowflake; return (rows, truncated).

    Used by aggregation pushdown: the whole GROUP BY runs remotely and only the
    (small) result crosses the wire. Egress is bounded by `fetch_cap`.
    """
    sf = (connector_factory or _connect)(source)
    try:
        cur = sf.cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchmany(fetch_cap + 1)
        finally:
            cur.close()
    finally:
        sf.close()
    truncated = len(rows) > fetch_cap
    rows = [tuple(_coerce(v) for v in row) for row in rows[:fetch_cap]]
    return rows, truncated


def _coerce(value: Any) -> Any:
    """Make connector values JSON-serializable (NUMBER -> float)."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value
