"""Shared data models for sources and query results."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

__all__ = ["Source", "SourceType", "QueryResult", "DiffResult"]


class SourceType(StrEnum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"
    EXCEL = "excel"
    ICEBERG = "iceberg"
    DELTA = "delta"
    DUCKDB = "duckdb"
    BIGQUERY = "bigquery"
    MSSQL = "mssql"
    SNOWFLAKE = "snowflake"
    MOTHERDUCK = "motherduck"
    ICEBERG_REST = "iceberg_rest"
    DUCKLAKE = "ducklake"


#: Source types registered via DuckDB ATTACH (one catalog per source).
ATTACH_TYPES = {
    SourceType.POSTGRES,
    SourceType.MYSQL,
    SourceType.SQLITE,
    SourceType.DUCKDB,
    SourceType.BIGQUERY,
    SourceType.MSSQL,
    SourceType.MOTHERDUCK,
    SourceType.ICEBERG_REST,
    SourceType.DUCKLAKE,
}

#: ATTACH types that ship as DuckDB community extensions (auto-installed).
COMMUNITY_ATTACH_EXTENSIONS = {SourceType.BIGQUERY: "bigquery", SourceType.MSSQL: "mssql"}

#: Source types with no reliable ATTACH; materialized via a Python connector.
CONNECTOR_TYPES = {SourceType.SNOWFLAKE}

#: Source types registered as views over file/table readers.
FILE_TYPES = {
    SourceType.CSV,
    SourceType.PARQUET,
    SourceType.JSON,
    SourceType.EXCEL,
    SourceType.ICEBERG,
    SourceType.DELTA,
}


class Source(BaseModel):
    """A charter-defined data source with credentials already resolved."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    type: SourceType
    connection: dict[str, str | int] = Field(default_factory=dict)
    credentials: dict[str, str] = Field(default_factory=dict)
    path: str | None = None
    tables: list[str] = Field(default_factory=list)
    pii: dict[str, list[str]] = Field(default_factory=dict)
    #: Agent-access overrides (on=real, off=masked) at source/table/column level.
    agent_access: dict = Field(default_factory=dict)
    #: Per-table prose context for agents (table -> guidance), from `context:`.
    table_context: dict[str, str] = Field(default_factory=dict)
    #: Row-level filters for the agent surface: table -> SQL boolean predicate.
    row_filters: dict[str, str] = Field(default_factory=dict)
    #: Connector-extract cap (Snowflake). Overrides the engine default; ignored
    #: for ATTACH/file sources, which stream and are not row-capped.
    max_rows: int | None = Field(default=None, gt=0)


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[tuple]
    row_count: int
    truncated: bool = False
    #: Non-fatal advisories (e.g. a connector source hit its extract cap).
    warnings: list[str] = Field(default_factory=list)
    #: Source relations/columns the query read (SELECT only); None when unavailable.
    #: Keys: `relations`/`columns` (list[str]) and an optional nested `lineage` map.
    provenance: dict | None = None
    #: Profiling only: per-column [value, count] top-frequency lists.
    top_values: dict[str, list] | None = None


class DiffResult(BaseModel):
    """Full-row set difference between two relations. Sample rows are row-capped;
    the *_count fields are the true totals."""

    columns: list[str]
    left_only: list[tuple]
    right_only: list[tuple]
    left_only_count: int
    right_only_count: int
    common_count: int
    #: With a key: rows whose key matches but whose values differ. None otherwise.
    #: (With a key, the *_only counts are by key — removed / added — and
    #: common_count is the number of matched keys.)
    changed_count: int | None = None
    truncated: bool = False
