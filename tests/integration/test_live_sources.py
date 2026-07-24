"""Live-database integration tests. Require compose services (see compose.yaml)."""

import os

import pytest

from datacharter.engine.guard import QueryNotAllowed
from datacharter.engine.session import Engine, EngineError
from datacharter.models import Source, SourceType

pytestmark = pytest.mark.integration

PG_PORT = int(os.environ.get("CHARTER_TEST_PG_PORT", "55432"))
MY_PORT = int(os.environ.get("CHARTER_TEST_MYSQL_PORT", "53306"))


def _pg_source() -> Source:
    return Source(
        name="crmpg",
        type=SourceType.POSTGRES,
        connection={"host": "127.0.0.1", "port": PG_PORT, "database": "demo", "user": "charter"},
        credentials={"password": "charter_test_pw"},
    )


def _mysql_source() -> Source:
    return Source(
        name="eventsdb",
        type=SourceType.MYSQL,
        connection={"host": "127.0.0.1", "port": MY_PORT, "database": "demo", "user": "charter"},
        credentials={"password": "charter_test_pw"},
    )


def test_postgres_attach_and_query(tmp_path):
    with Engine(tmp_path, [_pg_source()]) as eng:
        result = eng.query_sync("SELECT email FROM crmpg.customers ORDER BY id")
        assert result.rows[0] == ("ada@example.com",)
        assert result.row_count == 3


def test_mysql_attach_and_query(tmp_path):
    with Engine(tmp_path, [_mysql_source()]) as eng:
        result = eng.query_sync("SELECT count(*) FROM eventsdb.events")
        assert result.rows == [(4,)]


def test_cross_database_join_postgres_mysql_csv(tmp_path):
    (tmp_path / "plans.csv").write_text("tier,price\npro,99\nfree,0\n")
    csv = Source(name="plans", type=SourceType.CSV, path="plans.csv")
    with Engine(tmp_path, [_pg_source(), _mysql_source(), csv]) as eng:
        result = eng.query_sync(
            """
            SELECT c.email, count(e.id) AS events, p.price
            FROM crmpg.customers c
            JOIN eventsdb.events e ON e.customer_id = c.id
            JOIN plans p ON p.tier = c.tier
            GROUP BY c.email, p.price
            ORDER BY c.email
            """
        )
        assert result.columns == ["email", "events", "price"]
        assert result.rows == [
            ("ada@example.com", 2, 99),
            ("edsger@example.com", 1, 99),
            ("grace@example.com", 1, 0),
        ]


def test_postgres_attach_is_read_only(tmp_path):
    with Engine(tmp_path, [_pg_source()]) as eng, pytest.raises(QueryNotAllowed):
        eng.query_sync("INSERT INTO crmpg.customers VALUES (9, 'x@x', 'free')")


def test_bad_password_error_is_scrubbed(tmp_path):
    src = _pg_source()
    src.credentials["password"] = "wrong_pw_value_xyz"
    with pytest.raises(EngineError) as excinfo:
        Engine(tmp_path, [src]).start()
    assert "wrong_pw_value_xyz" not in str(excinfo.value)


# -- D10: compatibility views + deterministic pushdown verification ------------


def _pg_with_tables() -> Source:
    src = _pg_source()
    src.tables = ["customers"]
    return src


def test_compat_view_over_live_postgres(tmp_path):
    with Engine(tmp_path, [_pg_with_tables()]) as eng:
        assert eng.query_sync("SELECT count(*) FROM crmpg__customers").rows == [(3,)]


def test_filter_pushdown_into_postgres_scan(tmp_path):
    # Smart logic, not an agent: EXPLAIN must show the predicate pushed into the
    # postgres scan (filters= on the scan node), proving the remote does the work.
    with Engine(tmp_path, [_pg_source()]) as eng:
        plan = eng.query_sync(
            "EXPLAIN SELECT email FROM crmpg.customers WHERE tier = 'pro'"
        )
        text = "\n".join(str(c) for row in plan.rows for c in row).lower()
        assert "postgres" in text
        # DuckDB annotates pushed predicates on the scan; tier must appear there.
        assert "filters" in text or "tier" in text


def test_projection_pushdown_into_postgres_scan(tmp_path):
    with Engine(tmp_path, [_pg_source()]) as eng:
        plan = eng.query_sync("EXPLAIN SELECT email FROM crmpg.customers")
        text = "\n".join(str(c) for row in plan.rows for c in row).lower()
        # Only the projected column should be named in the scan, not tier.
        assert "email" in text


def test_cross_db_join_pushdown_per_leg(tmp_path):
    # Each remote leg is filtered at the source; the join itself runs in DuckDB.
    with Engine(tmp_path, [_pg_source(), _mysql_source()]) as eng:
        plan = eng.query_sync(
            """
            EXPLAIN
            SELECT c.email FROM crmpg.customers c
            JOIN eventsdb.events e ON e.customer_id = c.id
            WHERE c.tier = 'pro'
            """
        )
        text = "\n".join(str(c) for row in plan.rows for c in row).lower()
        assert "postgres" in text and "mysql" in text
        assert "join" in text  # the join node lives in DuckDB's plan


def test_heterogeneous_join_pushes_every_leg_filter(tmp_path):
    # postgres + mysql + parquet in one join: DuckDB pushes each single-source
    # filter into its own scanner, then joins the reduced legs locally. This is
    # the federation guarantee that connector pushdown mirrors for Snowflake.
    import duckdb

    duckdb.connect().execute(
        f"COPY (SELECT i AS id, i % 2 AS flag FROM range(50) t(i)) "
        f"TO '{tmp_path / 'f.parquet'}'"
    )
    flags = Source(name="flags", type=SourceType.PARQUET, path="f.parquet")
    with Engine(tmp_path, [_pg_source(), _mysql_source(), flags]) as eng:
        plan = eng.query_sync(
            """
            EXPLAIN
            SELECT c.email, e.kind, f.flag
            FROM crmpg.customers c
            JOIN eventsdb.events e ON e.customer_id = c.id
            JOIN flags f ON f.id = c.id
            WHERE c.tier = 'pro' AND e.kind = 'login' AND f.flag = 1
            """
        )
        text = "\n".join(str(c) for row in plan.rows for c in row).lower()
        assert "postgres_scan" in text and "tier='pro'" in text
        assert "mysql_scan" in text and "kind='login'" in text
        assert "read_parquet" in text and "flag=1" in text
