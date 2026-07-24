import pytest

from datacharter.engine.guard import QueryNotAllowed, ensure_allowed


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  select * from t  ",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "FROM t SELECT a",
        "VALUES (1, 2)",
        "EXPLAIN SELECT 1",
        "DESCRIBE t",
        "SHOW TABLES",
        "SUMMARIZE t",
        "SELECT 1;",
        "-- lead comment\nSELECT 1",
        "/* block */ SELECT 1",
    ],
)
def test_read_statements_allowed(sql):
    assert ensure_allowed(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE local.snap AS SELECT 1",
        "create or replace table local.snap as select 1",
        "DROP TABLE local.snap",
        "drop table if exists local . snap",
    ],
)
def test_local_ddl_allowed(sql):
    assert ensure_allowed(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM t",
        "UPDATE t SET a = 1",
        "INSERT INTO t VALUES (1)",
        "DROP TABLE t",
        "CREATE TABLE main.x AS SELECT 1",
        "ATTACH 'x.db' AS y",
        "SET temp_directory = '/tmp'",
        "INSTALL httpfs",
        "COPY t TO 'out.csv'",
        "/* sneak */ DELETE FROM t",
        "-- sneak\nDROP TABLE t",
        "SELECT 1; DELETE FROM t",
        "",
        "   ",
    ],
)
def test_writes_and_tricks_blocked(sql):
    with pytest.raises(QueryNotAllowed):
        ensure_allowed(sql)


def test_semicolon_inside_string_is_fine():
    assert ensure_allowed("SELECT 'a;b' AS s")


# -- Verified audit bypasses (must all be blocked) -----------------------------


@pytest.mark.parametrize(
    "sql",
    [
        # DC-SEC-001: dollar-quote desync → statement stacking → ATTACH/INSTALL.
        "SELECT $$'$$ AS a; ATTACH '/tmp/evil.db' AS e",
        "SELECT 1; INSTALL httpfs",
        # DC-SEC-002: EXPLAIN ANALYZE COPY → arbitrary file write.
        "EXPLAIN ANALYZE COPY (SELECT 1) TO '/tmp/exfil.csv'",
        "EXPLAIN COPY (SELECT 1) TO '/tmp/exfil.csv'",
        # DC-SEC-003: CTE-prefixed DML sneaks past a first-word filter.
        "WITH d AS (SELECT 1) DELETE FROM t",
        "WITH d AS (SELECT 1) UPDATE t SET a = 1",
        "WITH d AS (SELECT 1) INSERT INTO t VALUES (1)",
        # Settings changes (incl. re-enabling external access) type as SET.
        "PRAGMA enable_external_access=true",
        "PRAGMA memory_limit='1GB'",
        "CALL pragma_table_info('t')",
        "DETACH x",
        "LOAD httpfs",
    ],
)
def test_audit_bypasses_blocked(sql):
    with pytest.raises(QueryNotAllowed):
        ensure_allowed(sql)


@pytest.mark.parametrize(
    "sql",
    [
        # DC-SEC-004: arbitrary file read via fs functions in a plain SELECT.
        "SELECT * FROM read_csv('/etc/hosts')",
        "SELECT * FROM read_parquet('/etc/hosts')",
        "SELECT read_text('/etc/hosts')",
        "SELECT * FROM glob('/etc/*')",
        # SSRF via remote scanners called directly.
        "SELECT * FROM postgres_scan('host=evil', 'public', 't')",
        # Hidden inside a CTE, a subquery, EXPLAIN, or the local-DDL write path.
        "WITH x AS (SELECT * FROM read_csv('/etc/hosts')) SELECT * FROM x",
        "SELECT * FROM (SELECT * FROM read_csv('/etc/hosts')) q",
        "EXPLAIN SELECT * FROM read_csv('/etc/hosts')",
        "CREATE TABLE local.t AS SELECT * FROM read_csv('/etc/passwd')",
    ],
)
def test_filesystem_and_remote_functions_blocked(sql):
    with pytest.raises(QueryNotAllowed):
        ensure_allowed(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "EXPLAIN SELECT 1",
        "EXPLAIN ANALYZE SELECT 1",
        "EXPLAIN WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT * FROM range(100)",  # safe table function stays allowed
        "SELECT unnest([1, 2, 3])",
    ],
)
def test_explain_and_safe_functions_allowed(sql):
    assert ensure_allowed(sql)
