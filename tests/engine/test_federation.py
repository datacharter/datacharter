"""Compatibility-view aliasing + Snowflake connector fallback (D10, unit-level)."""

import sqlite3

import pytest

from datacharter.engine.session import Engine
from datacharter.engine.snowflake import materialize_snowflake
from datacharter.engine.sources import compatibility_view_sql, qualified_name
from datacharter.models import Source, SourceType


def test_qualified_name_per_source_scheme():
    pg = Source(name="pg", type=SourceType.POSTGRES, connection={"schema": "sales"})
    assert qualified_name(pg, "orders") == "pg.sales.orders"
    my = Source(name="shop", type=SourceType.MYSQL, connection={"database": "app"})
    assert qualified_name(my, "events") == "shop.app.events"
    lite = Source(name="crm", type=SourceType.SQLITE)
    assert qualified_name(lite, "accounts") == "crm.main.accounts"
    bq = Source(name="wh", type=SourceType.BIGQUERY, connection={"dataset": "core"})
    assert qualified_name(bq, "t") == "wh.core.t"
    ms = Source(name="legacy", type=SourceType.MSSQL, connection={"schema": "dbo"})
    assert qualified_name(ms, "t") == "legacy.dbo.t"


def test_qualified_name_rejects_injection():
    from datacharter.engine.sources import SourceConfigError

    pg = Source(name="pg", type=SourceType.POSTGRES)
    with pytest.raises(SourceConfigError):
        qualified_name(pg, "orders; DROP TABLE x")


def test_compat_view_flat_alias():
    pg = Source(name="crmpg", type=SourceType.POSTGRES, connection={"schema": "public"})
    (stmt,) = compatibility_view_sql(pg, ["customers"])
    assert '"crmpg__customers"' in stmt
    assert "crmpg.public.customers" in stmt


def test_sqlite_source_with_tables_gets_compat_views(tmp_path):
    db = tmp_path / "crm.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.execute("INSERT INTO accounts VALUES (1, 'acme')")
    con.commit()
    con.close()
    src = Source(name="crm", type=SourceType.SQLITE, path="crm.db", tables=["accounts"])
    with Engine(tmp_path, [src]) as eng:
        # Both the qualified name AND the flat compat alias resolve.
        assert eng.query_sync("SELECT org FROM crm.main.accounts").rows == [("acme",)]
        assert eng.query_sync("SELECT org FROM crm__accounts").rows == [("acme",)]


def test_cross_source_join_via_compat_aliases(tmp_path):
    db = tmp_path / "crm.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE accounts (id INTEGER, tier TEXT)")
    con.execute("INSERT INTO accounts VALUES (1, 'pro'), (2, 'free')")
    con.commit()
    con.close()
    (tmp_path / "plans.csv").write_text("tier,price\npro,99\nfree,0\n")

    crm = Source(name="crm", type=SourceType.SQLITE, path="crm.db", tables=["accounts"])
    plans = Source(name="plans", type=SourceType.CSV, path="plans.csv")
    with Engine(tmp_path, [crm, plans]) as eng:
        result = eng.query_sync(
            "SELECT a.id, p.price FROM crm__accounts a "
            "JOIN plans p ON p.tier = a.tier ORDER BY a.id"
        )
        assert result.rows == [(1, 99), (2, 0)]


# -- Snowflake fallback (fake connector; no live Snowflake) --------------------


class _FakeCursor:
    def __init__(self, rows, description):
        self._rows = rows
        self.description = description
        self.executed = None

    def execute(self, sql):
        self.executed = sql

    def fetchmany(self, n):
        batch, self._rows = self._rows[:n], self._rows[n:]
        return batch

    def close(self):
        pass


class _FakeSnowflake:
    def __init__(self, rows, description):
        self._rows = rows
        self._description = description
        self.last_cursor = None

    def cursor(self):
        self.last_cursor = _FakeCursor(list(self._rows), self._description)
        return self.last_cursor

    def close(self):
        pass


def test_snowflake_materializes_into_local_table(tmp_path):
    import duckdb

    desc = [
        ("id", 0, None, None, None, None, None),
        ("name", 2, None, None, None, None, None),
    ]
    fake = _FakeSnowflake(rows=[(1, "ada"), (2, "grace")], description=desc)
    src = Source(
        name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"}, tables=["users"]
    )
    conn = duckdb.connect()
    materialize_snowflake(conn, src, ["users"], connector_factory=lambda _s: fake)

    rows = conn.execute('SELECT name FROM "wh__users" ORDER BY id').fetchall()
    assert rows == [("ada",), ("grace",)]
    # Filter/projection is pushed to Snowflake at extract time via the SELECT.
    assert "FROM users" in fake.last_cursor.executed
    assert "LIMIT" in fake.last_cursor.executed


def test_snowflake_extract_honors_pushdown(tmp_path):
    import duckdb

    from datacharter.engine.pushdown import Pushdown

    desc = [("email", 2, None, None, None, None, None)]
    fake = _FakeSnowflake(rows=[("ada@x.com",)], description=desc)
    src = Source(
        name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"}, tables=["users"]
    )
    conn = duckdb.connect()
    materialize_snowflake(
        conn,
        src,
        ["users"],
        pushdowns={"users": Pushdown(columns={"email"}, predicates=["tier = 'pro'"])},
        connector_factory=lambda _s: fake,
    )
    sql = fake.last_cursor.executed
    # Probe is cap+1 so a full result is detectable as truncation.
    assert sql == "SELECT email FROM users WHERE tier = 'pro' LIMIT 1000001"


def test_engine_lazy_pushdown_end_to_end(tmp_path, monkeypatch):
    # Full path: engine parses the user query, pushes the filter into the extract,
    # materializes lazily, and returns correct rows.
    from datacharter.engine import snowflake as sf_mod

    desc = [
        ("id", 0, None, None, None, None, None),
        ("email", 2, None, None, None, None, None),
        ("tier", 2, None, None, None, None, None),
    ]
    seen = {}

    def fake_factory(_source):
        fake = _FakeSnowflake(rows=[(1, "ada@x.com", "pro")], description=desc)
        seen["fake"] = fake
        return fake

    monkeypatch.setattr(sf_mod, "_connect", fake_factory)
    src = Source(
        name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"}, tables=["users"]
    )
    with Engine(tmp_path, [src]) as eng:
        # Nothing extracted until the table is queried (lazy).
        assert "fake" not in seen
        result = eng.query_sync("SELECT email FROM wh__users WHERE tier='pro'")
        assert result.rows == [("ada@x.com",)]
        # The engine pushed projection + filter into the remote SELECT.
        assert seen["fake"].last_cursor.executed == (
            "SELECT email, tier FROM users WHERE tier = 'pro' LIMIT 1000001"
        )


def test_engine_re_extracts_on_filter_change(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    desc = [("id", 0, None, None, None, None, None), ("tier", 2, None, None, None, None, None)]
    calls = []

    def fake_factory(_source):
        fake = _FakeSnowflake(rows=[(1, "pro")], description=desc)
        calls.append(fake)
        return fake

    monkeypatch.setattr(sf_mod, "_connect", fake_factory)
    src = Source(
        name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"}, tables=["users"]
    )
    with Engine(tmp_path, [src]) as eng:
        eng.query_sync("SELECT id FROM wh__users WHERE tier='pro'")
        eng.query_sync("SELECT id FROM wh__users WHERE tier='pro'")  # same shape -> cached
        assert len(calls) == 1
        eng.query_sync("SELECT id FROM wh__users WHERE tier='free'")  # new filter -> re-extract
        assert len(calls) == 2


# -- D12: extract cap (configurable) + truncation honesty ----------------------


def test_max_rows_caps_extract_and_reports_truncation(tmp_path):
    import duckdb

    desc = [("id", 0, None, None, None, None, None)]
    fake = _FakeSnowflake(rows=[(1,), (2,), (3,)], description=desc)
    src = Source(
        name="wh",
        type=SourceType.SNOWFLAKE,
        connection={"account": "x"},
        tables=["users"],
        max_rows=2,
    )
    conn = duckdb.connect()
    result = materialize_snowflake(conn, src, ["users"], connector_factory=lambda _s: fake)
    assert result == {"users": 2}  # truncated at the cap of 2
    assert conn.execute('SELECT count(*) FROM "wh__users"').fetchone() == (2,)


def test_engine_surfaces_truncation_warning(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    desc = [("id", 0, None, None, None, None, None)]
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake(rows=[(1,), (2,), (3,)], description=desc)
    )
    src = Source(
        name="wh",
        type=SourceType.SNOWFLAKE,
        connection={"account": "x"},
        tables=["users"],
        max_rows=2,
    )
    with Engine(tmp_path, [src]) as eng:
        result = eng.query_sync("SELECT id FROM wh__users")
        assert result.truncated is False  # only 2 rows returned, under the 10k grid cap
        assert result.warnings and "extract cap" in result.warnings[0]
        assert "2" in result.warnings[0]


def test_no_truncation_no_warning(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    desc = [("id", 0, None, None, None, None, None)]
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake(rows=[(1,), (2,)], description=desc)
    )
    src = Source(
        name="wh",
        type=SourceType.SNOWFLAKE,
        connection={"account": "x"},
        tables=["users"],
        max_rows=5,
    )
    with Engine(tmp_path, [src]) as eng:
        assert eng.query_sync("SELECT id FROM wh__users").warnings == []


def test_snowflake_source_requires_tables(tmp_path):
    from datacharter.engine.session import EngineError

    src = Source(name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"})
    with pytest.raises(EngineError, match="requires an explicit tables"):
        Engine(tmp_path, [src]).start()
