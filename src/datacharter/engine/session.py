"""Engine: one DuckDB session with spill hygiene, guarded queries, local catalog."""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import re
import shutil
import threading
from collections.abc import Sequence
from pathlib import Path

import duckdb

from datacharter.engine.aggregate import build_remote_aggregation
from datacharter.engine.guard import ensure_allowed
from datacharter.engine.provenance import extract_provenance
from datacharter.engine.pushdown import extract_pushdown
from datacharter.engine.scrub import scrub
from datacharter.engine.snowflake import _cap_for, materialize_snowflake, run_snowflake_sql
from datacharter.engine.sources import compatibility_view_sql, registration_sql
from datacharter.models import (
    ATTACH_TYPES,
    COMMUNITY_ATTACH_EXTENSIONS,
    CONNECTOR_TYPES,
    FILE_TYPES,
    DiffResult,
    QueryResult,
    Source,
)

__all__ = ["Engine", "EngineError", "QueryTimeout"]

STATE_DIR = ".datacharter"
DEFAULT_ROW_LIMIT = 10_000
_STAGE_TABLE = "_dc_remote_agg"  # temp table staging a pushed aggregation's result


class EngineError(Exception):
    """Engine failure with credentials scrubbed from the message."""


class QueryTimeout(EngineError):
    """Query exceeded its timeout and was interrupted."""


def _valid_relation(relation: str) -> bool:
    """A safe 1–3 part relation name (catalog.schema.table) — no SQL injection."""
    parts = relation.split(".")
    return 1 <= len(parts) <= 3 and all(
        p and all(ch.isalnum() or ch == "_" for ch in p) for p in parts
    )


class Engine:
    """DuckDB session bound to a workspace directory.

    Lifecycle: construct → start() → query()/query_sync() → close().
    Spill hygiene per DESIGN D8: contained temp dir, encrypted temp files,
    wipe on start and close.
    """

    def __init__(
        self,
        workspace: Path | str,
        sources: Sequence[Source] = (),
        *,
        local_key: str | None = None,
        allow_spill: bool = True,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.sources = list(sources)
        self._local_key = local_key
        self._allow_spill = allow_spill
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._query_lock = asyncio.Lock()
        # Serializes all sync DB access — query/export/snapshot/upload run in
        # separate threads (to_thread) over one connection; this prevents races.
        self._exec_lock = threading.RLock()
        self._secret_values: set[str] = set()
        # Connector sources materialize lazily: alias -> (source, remote table).
        self._connector_aliases: dict[str, tuple[Source, str]] = {}
        # alias -> pushdown signature currently materialized (re-extract on change).
        self._materialized: dict[str, tuple] = {}
        # alias -> cap that truncated its last extract (None/absent = complete).
        self._truncated: dict[str, int | None] = {}
        for src in self.sources:
            self._secret_values.update(str(v) for v in src.credentials.values())

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> Engine:
        state = self.workspace / STATE_DIR
        tmp = state / "tmp"
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)

        self._conn = duckdb.connect()
        self._setup("SET temp_directory = " + self._quoted(str(tmp)))
        self._setup("SET temp_file_encryption = true")
        if not self._allow_spill:
            self._setup("SET max_temp_directory_size = '0'")
        self._attach_local(state)
        for src in self.sources:
            self._register(src)
        return self

    def _register(self, src: Source) -> None:
        """Register one source: extensions, attach/view, then compatibility aliases."""
        ext = COMMUNITY_ATTACH_EXTENSIONS.get(src.type)
        if ext is not None:
            self._setup(f"INSTALL {ext} FROM community")
            self._setup(f"LOAD {ext}")
        if src.type in CONNECTOR_TYPES:
            self._register_connector(src)
            return
        for stmt in registration_sql(src, self.workspace):
            self._setup(stmt)
        if src.type in ATTACH_TYPES and src.tables:
            for stmt in compatibility_view_sql(src, src.tables):
                self._setup(stmt)

    def _register_connector(self, src: Source) -> None:
        """Record a connector source for lazy, predicate-aware materialization."""
        if not src.tables:
            raise EngineError(
                f"Source '{src.name}' ({src.type.value}) requires an explicit tables: "
                "list — connector sources are materialized table by table."
            )
        for table in src.tables:
            self._connector_aliases[f"{src.name}__{table}".lower()] = (src, table)

    def _ensure_connectors(self, sql: str) -> list[str]:
        """Materialize any connector tables this query touches, pushing its filters.

        Re-extracts only when the query's projection/filter signature changes;
        the full WHERE still runs locally, so a narrow extract stays correct.
        Returns warnings for any referenced table whose extract hit its cap.
        """
        if not self._connector_aliases:
            return []
        conn = self._require_conn()
        pushdowns = extract_pushdown(conn, sql, set(self._connector_aliases))
        warnings: list[str] = []
        for alias, pushdown in pushdowns.items():
            src, table = self._connector_aliases[alias]
            cols = None if pushdown.columns is None else tuple(sorted(pushdown.columns))
            signature = (cols, tuple(pushdown.predicates))
            if self._materialized.get(alias) != signature:
                try:
                    result = materialize_snowflake(conn, src, [table], pushdowns={table: pushdown})
                except Exception as exc:
                    raise self._wrap(exc) from None
                self._materialized[alias] = signature
                self._truncated[alias] = result.get(table)
            cap = self._truncated.get(alias)
            if cap:
                warnings.append(
                    f"Source '{alias}' hit its {cap:,}-row extract cap; results reflect "
                    f"only the first {cap:,} rows. Add a WHERE filter, aggregate, or "
                    f"raise max_rows in charter.yaml."
                )
        return warnings

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        shutil.rmtree(self.workspace / STATE_DIR / "tmp", ignore_errors=True)

    def __enter__(self) -> Engine:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- queries -----------------------------------------------------------

    def query_sync(self, sql: str, *, row_limit: int = DEFAULT_ROW_LIMIT) -> QueryResult:
        """Run one guarded statement; returns capped rows with read provenance."""
        result = self._execute(sql, row_limit=row_limit)
        result.provenance = extract_provenance(sql)
        return result

    def _execute(self, sql: str, *, row_limit: int = DEFAULT_ROW_LIMIT) -> QueryResult:
        conn = self._require_conn()
        normalized = ensure_allowed(sql)
        with self._exec_lock:
            if self._connector_aliases:
                pushed = self._try_remote_aggregation(normalized, row_limit)
                if pushed is not None:
                    return pushed
            warnings = self._ensure_connectors(normalized)
            try:
                cursor = conn.execute(normalized)
                columns = [d[0] for d in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(row_limit + 1) if columns else []
            except duckdb.Error as exc:
                raise self._wrap(exc) from None
        truncated = len(rows) > row_limit
        rows = rows[:row_limit]
        return QueryResult(
            columns=columns, rows=rows, row_count=len(rows), truncated=truncated, warnings=warnings
        )

    def _try_remote_aggregation(self, sql: str, row_limit: int) -> QueryResult | None:
        """Push a single-table aggregation to the remote; None to fall back.

        The GROUP BY runs on the connector; only the small result crosses the
        wire — no million-row raw extract. On any failure we return None and the
        raw-extract path (still correct) takes over.
        """
        agg = build_remote_aggregation(self._require_conn(), sql, set(self._connector_aliases))
        if agg is None:
            return None
        src, table = self._connector_aliases[agg.alias]
        try:
            rows, truncated = run_snowflake_sql(src, agg.render(table), row_limit)
        except Exception:
            return None
        warnings = []
        if truncated:
            warnings.append(
                f"Aggregation on '{agg.alias}' produced more than {row_limit:,} groups; "
                f"showing the first {row_limit:,}."
            )
        return QueryResult(
            columns=agg.columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            warnings=warnings,
        )

    def _stage_remote_aggregation(self, sql: str) -> str | None:
        """Run a pushable aggregation on the remote, stage its (small) result in a
        temp table, and return that table's name; None to use the raw path.

        Lets export/snapshot compute a single-table aggregation whole on the
        connector instead of raw-extracting (and capping) millions of rows to
        aggregate locally. Egress is bounded by the source's extract cap, matching
        the raw path. Any failure -> None and the caller's raw path (still correct).
        """
        if not self._connector_aliases:
            return None
        conn = self._require_conn()
        agg = build_remote_aggregation(conn, sql, set(self._connector_aliases))
        if agg is None:
            return None
        src, table = self._connector_aliases[agg.alias]
        try:
            rows, _ = run_snowflake_sql(src, agg.render(table), _cap_for(src))
        except Exception:
            return None
        types = _duckdb_types(agg.columns, rows)
        col_defs = ", ".join(f'"{c}" {t}' for c, t in zip(agg.columns, types, strict=True))
        conn.execute(f"CREATE OR REPLACE TEMP TABLE {_STAGE_TABLE} ({col_defs})")
        if rows:
            placeholders = ", ".join("?" for _ in agg.columns)
            conn.executemany(f"INSERT INTO {_STAGE_TABLE} VALUES ({placeholders})", rows)
        return _STAGE_TABLE

    async def query(
        self,
        sql: str,
        *,
        timeout_s: float = 60.0,
        row_limit: int = DEFAULT_ROW_LIMIT,
    ) -> QueryResult:
        """Async wrapper around query_sync with interrupt-based timeout.

        Serialized per engine: one connection, one in-flight query — keeps
        interrupt() scoped to the query that armed the timer.
        """
        conn = self._require_conn()
        async with self._query_lock:
            return await self._query_locked(conn, sql, timeout_s, row_limit)

    async def diff(
        self,
        left: str,
        right: str,
        *,
        key: list[str] | None = None,
        row_limit: int = DEFAULT_ROW_LIMIT,
    ) -> DiffResult:
        """Difference between two relations (cross-source aware).

        Without `key`: a full-row set difference — rows only in each side plus the
        common count. With `key`: rows are matched on the key columns, so the
        *_only counts become removed / added and `changed_count` reports keys that
        match but whose values differ. Both relations must expose the same
        columns; the read-only guard applies to every underlying query.
        """
        for rel in (left, right):
            if not _valid_relation(rel):
                raise EngineError(f"Invalid relation name: {rel!r}")
        if key:
            return await self._diff_by_key(left, right, key, row_limit)
        left_sql = f"SELECT * FROM {left} EXCEPT SELECT * FROM {right}"
        right_sql = f"SELECT * FROM {right} EXCEPT SELECT * FROM {left}"
        left_only = await self.query(left_sql, row_limit=row_limit)
        right_only = await self.query(right_sql, row_limit=row_limit)
        left_count = (await self.query(f"SELECT count(*) FROM ({left_sql})")).rows[0][0]
        right_count = (await self.query(f"SELECT count(*) FROM ({right_sql})")).rows[0][0]
        common = (
            await self.query(
                f"SELECT count(*) FROM (SELECT * FROM {left} INTERSECT SELECT * FROM {right})"
            )
        ).rows[0][0]
        return DiffResult(
            columns=left_only.columns,
            left_only=left_only.rows,
            right_only=right_only.rows,
            left_only_count=left_count,
            right_only_count=right_count,
            common_count=common,
            truncated=left_only.truncated or right_only.truncated,
        )

    async def _diff_by_key(
        self, left: str, right: str, key: list[str], row_limit: int
    ) -> DiffResult:
        for col in key:
            if not (col and all(ch.isalnum() or ch == "_" for ch in col)):
                raise EngineError(f"Invalid key column: {col!r}")
        keys = ", ".join(key)
        removed_sql = f"SELECT * FROM {left} WHERE ({keys}) NOT IN (SELECT {keys} FROM {right})"
        added_sql = f"SELECT * FROM {right} WHERE ({keys}) NOT IN (SELECT {keys} FROM {left})"
        removed = await self.query(removed_sql, row_limit=row_limit)
        added = await self.query(added_sql, row_limit=row_limit)
        removed_count = (await self.query(f"SELECT count(*) FROM ({removed_sql})")).rows[0][0]
        added_count = (await self.query(f"SELECT count(*) FROM ({added_sql})")).rows[0][0]
        matched = (
            await self.query(
                f"SELECT count(*) FROM (SELECT {keys} FROM {left} "
                f"INTERSECT SELECT {keys} FROM {right})"
            )
        ).rows[0][0]
        identical = (
            await self.query(
                f"SELECT count(*) FROM (SELECT * FROM {left} INTERSECT SELECT * FROM {right})"
            )
        ).rows[0][0]
        return DiffResult(
            columns=removed.columns,
            left_only=removed.rows,
            right_only=added.rows,
            left_only_count=removed_count,
            right_only_count=added_count,
            common_count=matched,
            changed_count=matched - identical,
            truncated=removed.truncated or added.truncated,
        )

    async def _query_locked(
        self,
        conn: duckdb.DuckDBPyConnection,
        sql: str,
        timeout_s: float,
        row_limit: int,
    ) -> QueryResult:
        loop = asyncio.get_running_loop()
        timer = loop.call_later(timeout_s, conn.interrupt)
        try:
            return await asyncio.to_thread(self.query_sync, sql, row_limit=row_limit)
        except EngineError as exc:
            if timer.cancelled() or not timer.when() > loop.time():
                raise QueryTimeout(f"Query exceeded {timeout_s}s and was interrupted.") from None
            raise exc
        finally:
            timer.cancel()

    def add_source(self, source: Source) -> None:
        """Register an additional source on a running session (e.g. an upload)."""
        self._secret_values.update(str(v) for v in source.credentials.values())
        with self._exec_lock:
            self._register(source)
        self.sources.append(source)

    def remove_source(self, name: str) -> None:
        """Deregister a source: drop its views/materialized tables and detach."""
        with self._exec_lock:
            conn = self._require_conn()
            src = next((s for s in self.sources if s.name == name), None)
            for alias in [a for a, (s, _t) in self._connector_aliases.items() if s.name == name]:
                with contextlib.suppress(duckdb.Error):
                    conn.execute(f'DROP TABLE IF EXISTS "{alias}"')
                self._connector_aliases.pop(alias, None)
                self._materialized.pop(alias, None)
                self._truncated.pop(alias, None)
            if src is not None:
                if src.type in ATTACH_TYPES:
                    for table in src.tables:
                        alias = f"{name}__{table}".lower()
                        with contextlib.suppress(duckdb.Error):
                            conn.execute(f'DROP VIEW IF EXISTS "{alias}"')
                    with contextlib.suppress(duckdb.Error):
                        conn.execute(f"DETACH {name}")
                elif src.type in FILE_TYPES:
                    with contextlib.suppress(duckdb.Error):
                        conn.execute(f'DROP VIEW IF EXISTS "{name}"')
                self._secret_values.difference_update(str(v) for v in src.credentials.values())
            self.sources = [s for s in self.sources if s.name != name]

    def test_source(self, source: Source) -> None:
        """Probe a source in a throwaway connection; raise EngineError (scrubbed) on failure."""
        probe = duckdb.connect()
        try:
            ext = COMMUNITY_ATTACH_EXTENSIONS.get(source.type)
            if ext is not None:
                probe.execute(f"INSTALL {ext} FROM community")
                probe.execute(f"LOAD {ext}")
            if source.type in CONNECTOR_TYPES:
                from datacharter.engine.snowflake import _connect  # noqa: PLC0415

                _connect(source).close()
            else:
                for stmt in registration_sql(source, self.workspace):
                    probe.execute(stmt)
        except Exception as exc:
            raise self._wrap(exc) from None
        finally:
            probe.close()

    def export_sync(self, sql: str, fmt: str, dest: Path) -> Path:
        """Export a guarded read statement's result to dest (csv/parquet/json/xlsx)."""
        conn = self._require_conn()
        normalized = ensure_allowed(sql).rstrip(";").strip()
        formats = {"csv": "csv, HEADER", "parquet": "parquet", "json": "json", "xlsx": "xlsx"}
        if fmt not in formats:
            valid = ", ".join(formats)
            raise EngineError(f"Unsupported export format '{fmt}'. Use one of: {valid}.")
        with self._exec_lock:
            staged = self._stage_remote_aggregation(normalized)
            relation = staged if staged is not None else f"({normalized})"
            if staged is None:
                self._ensure_connectors(normalized)
            stmt = f"COPY {relation} TO {self._quoted(str(dest))} (FORMAT {formats[fmt]})"
            try:
                conn.execute(stmt)
            except duckdb.Error as exc:
                raise self._wrap(exc) from None
            finally:
                if staged is not None:
                    conn.execute(f"DROP TABLE IF EXISTS {staged}")
        return dest

    def snapshot_sync(self, sql: str, name: str) -> None:
        """Persist a guarded read statement's result as local.<name>."""
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
            raise EngineError("Snapshot name must be lowercase letters, digits, underscores.")
        normalized = ensure_allowed(sql).rstrip(";").strip()
        conn = self._require_conn()
        with self._exec_lock:
            staged = self._stage_remote_aggregation(normalized)
            select = f"(SELECT * FROM {staged})" if staged is not None else f"({normalized})"
            if staged is None:
                self._ensure_connectors(normalized)
            try:
                conn.execute(f"CREATE OR REPLACE TABLE local.{name} AS {select}")
            except duckdb.Error as exc:
                raise self._wrap(exc) from None
            finally:
                if staged is not None:
                    conn.execute(f"DROP TABLE IF EXISTS {staged}")

    # -- internals ----------------------------------------------------------

    def _attach_local(self, state: Path) -> None:
        db = state / "state.duckdb"
        options = ""
        if self._local_key is not None:
            options = f" (ENCRYPTION_KEY {self._quoted(self._local_key)})"
            self._secret_values.add(self._local_key)
        try:
            self._setup(f"ATTACH {self._quoted(str(db))} AS local{options}")
        except EngineError as exc:
            # A pre-existing state DB that won't open usually means the key
            # changed. It can hold saved snapshots, so never wipe it silently —
            # tell the user how to recover instead.
            if db.exists():
                raise EngineError(
                    f"Could not open the local state database ({STATE_DIR}/state.duckdb); "
                    "the encryption key may have changed. Restore the original key "
                    "(env DATACHARTER_STATE_KEY), or delete that file to start fresh "
                    "(this discards saved snapshots and history)."
                ) from None
            raise exc

    def _setup(self, stmt: str) -> None:
        conn = self._require_conn()
        try:
            conn.execute(stmt)
        except duckdb.Error as exc:
            raise self._wrap(exc) from None

    def _require_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise EngineError("Engine is not started. Call start() first.")
        return self._conn

    def _wrap(self, exc: Exception) -> EngineError:
        message = scrub(str(exc), self._secret_values)
        if isinstance(exc, duckdb.InterruptException):
            return QueryTimeout(message)
        return EngineError(message)

    @staticmethod
    def _quoted(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"


def _duckdb_types(columns: list[str], rows: list[tuple]) -> list[str]:
    """DuckDB column type per column, widened across ALL non-null values.

    Scan every value, not just the first: `_coerce` yields int for integral and
    float for fractional numbers, so one aggregate column can hold both. A
    first-value guess of BIGINT would let DuckDB SILENTLY truncate later floats,
    corrupting fractional sums/avgs. Results are small (the point of pushdown),
    so a full scan is cheap.
    """
    seen: list[set[str]] = [set() for _ in columns]
    for row in rows:
        for i, value in enumerate(row):
            if value is not None:
                seen[i].add(_duckdb_type(value))
    return [_resolve_type(s) for s in seen]


def _resolve_type(types: set[str]) -> str:
    if len(types) == 1:
        return next(iter(types))
    if types <= {"BIGINT", "DOUBLE"}:  # numeric mix -> widen to float, never truncate
        return "DOUBLE"
    return "VARCHAR"  # empty (all-null) or heterogeneous -> text is lossless


def _duckdb_type(value: object) -> str:
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "BIGINT"
    if isinstance(value, float):
        return "DOUBLE"
    if isinstance(value, datetime.datetime):
        return "TIMESTAMP"
    if isinstance(value, datetime.date):
        return "DATE"
    return "VARCHAR"
