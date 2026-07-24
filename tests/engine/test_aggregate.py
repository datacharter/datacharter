"""Aggregation pushdown (D12): AST reconstruction + engine remote-execution path."""

import duckdb
import pytest

from datacharter.engine.aggregate import build_remote_aggregation
from datacharter.engine.session import Engine
from datacharter.models import Source, SourceType

CONNECTORS = {"wh__sales"}


@pytest.fixture
def conn():
    c = duckdb.connect()
    yield c
    c.close()


def _agg(conn, sql):
    return build_remote_aggregation(conn, sql, CONNECTORS)


def test_global_count(conn):
    ra = _agg(conn, "SELECT count(*) FROM wh__sales")
    assert ra.render("sales") == "SELECT count(*) FROM sales"
    assert ra.columns == ["count_star()"]


def test_full_grouped_aggregation(conn):
    ra = _agg(
        conn,
        "SELECT region, count(*) AS n, sum(amount) AS rev, count(DISTINCT id) AS u "
        "FROM wh__sales WHERE tier='pro' GROUP BY region ORDER BY n DESC LIMIT 10",
    )
    assert ra.render("sales") == (
        "SELECT region, count(*) AS n, sum(amount) AS rev, count(DISTINCT id) AS u "
        "FROM sales WHERE tier = 'pro' GROUP BY region ORDER BY n DESC NULLS LAST LIMIT 10"
    )
    assert ra.columns == ["region", "n", "rev", "u"]


def test_multi_key_group_and_ordinal_order(conn):
    ra = _agg(
        conn, "SELECT region, tier, count(*) FROM wh__sales GROUP BY region, tier ORDER BY 3 DESC"
    )
    assert ra.render("sales") == (
        "SELECT region, tier, count(*) FROM sales GROUP BY region, tier ORDER BY 3 DESC NULLS LAST"
    )


def test_min_max_avg(conn):
    ra = _agg(conn, "SELECT min(amount), max(amount), avg(amount) FROM wh__sales")
    assert ra.render("sales") == "SELECT min(amount), max(amount), avg(amount) FROM sales"


@pytest.mark.parametrize(
    ("order", "expected"),
    [
        ("ORDER BY n", "ORDER BY n ASC NULLS LAST"),  # DuckDB default is NULLS LAST
        ("ORDER BY n ASC", "ORDER BY n ASC NULLS LAST"),
        ("ORDER BY n DESC", "ORDER BY n DESC NULLS LAST"),  # not Snowflake's DESC default
        ("ORDER BY 2 DESC", "ORDER BY 2 DESC NULLS LAST"),
        ("ORDER BY n ASC NULLS FIRST", "ORDER BY n ASC NULLS FIRST"),  # explicit honored
        ("ORDER BY n DESC NULLS FIRST", "ORDER BY n DESC NULLS FIRST"),
    ],
)
def test_order_by_carries_explicit_nulls(conn, order, expected):
    ra = _agg(conn, f"SELECT region, count(*) AS n FROM wh__sales GROUP BY region {order}")
    assert ra.render("sales") == (
        f"SELECT region, count(*) AS n FROM sales GROUP BY region {expected}"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM wh__sales",  # not an aggregation
        "SELECT region FROM wh__sales GROUP BY region",  # no aggregate
        "SELECT region, count(*) FROM wh__sales GROUP BY ROLLUP(region)",  # rollup
        "SELECT region, count(*) FROM wh__sales GROUP BY region HAVING count(*) > 5",  # having
        "SELECT count(*) FROM wh__sales WHERE upper(region) = 'X'",  # unpushable filter
        "SELECT count(*) FROM wh__sales a JOIN pg__x b ON b.id = a.id",  # join
        "SELECT count(*) FROM (SELECT * FROM wh__sales) t",  # subquery
        "SELECT region, count(*) FROM wh__sales GROUP BY lower(region)",  # grouped expression
    ],
)
def test_not_pushable_returns_none(conn, sql):
    assert _agg(conn, sql) is None


# -- Engine end-to-end via a fake connector ------------------------------------


class _FakeCursor:
    def __init__(self, rows, log):
        self._rows = list(rows)
        self._log = log

    def execute(self, sql):
        self._log.append(sql)

    def fetchmany(self, n):
        batch, self._rows = self._rows[:n], self._rows[n:]
        return batch

    @property
    def description(self):
        if not self._rows:
            return [("c0", 2, None, None, None, None, None)]
        # type_code 2 (VARCHAR) for strings, else 0 (NUMBER) — as the real driver does.
        return [
            (f"c{i}", 2 if isinstance(v, str) else 0, None, None, None, None, None)
            for i, v in enumerate(self._rows[0])
        ]

    def close(self):
        pass


class _FakeSnowflake:
    def __init__(self, rows, log):
        self._rows, self._log = rows, log

    def cursor(self):
        return _FakeCursor(self._rows, self._log)

    def close(self):
        pass


def _snowflake_source():
    return Source(
        name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"}, tables=["sales"]
    )


def test_engine_pushes_aggregation_not_raw_extract(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake([("north", 3), ("south", 1)], executed)
    )
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        result = eng.query_sync("SELECT region, count(*) AS n FROM wh__sales GROUP BY region")
        assert result.columns == ["region", "n"]
        assert result.rows == [("north", 3), ("south", 1)]
    # The remote ran the GROUP BY; no raw `SELECT * ... LIMIT` extract happened.
    assert executed == ["SELECT region, count(*) AS n FROM sales GROUP BY region"]


def test_engine_falls_back_to_raw_extract_when_not_pushable(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []

    def factory(_s):
        return _FakeSnowflake([(1, "north"), (2, "south")], executed)

    monkeypatch.setattr(sf_mod, "_connect", factory)
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        # SELECT * is not an aggregation -> raw extract path.
        eng.query_sync("SELECT * FROM wh__sales")
    assert executed and executed[0].startswith("SELECT * FROM sales")
    assert "LIMIT" in executed[0]


def test_export_pushes_aggregation_not_raw_extract(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake([("north", 3), ("south", 1)], executed)
    )
    dest = tmp_path / "out.csv"
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        eng.export_sync("SELECT region, count(*) AS n FROM wh__sales GROUP BY region", "csv", dest)
    # The remote ran the GROUP BY; no raw `SELECT * ... LIMIT` extract happened.
    assert executed == ["SELECT region, count(*) AS n FROM sales GROUP BY region"]
    text = dest.read_text()
    assert "region,n" in text and "north,3" in text and "south,1" in text


def test_export_falls_back_to_raw_extract_when_not_pushable(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake([(1, "north"), (2, "south")], executed)
    )
    dest = tmp_path / "out.csv"
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        eng.export_sync("SELECT * FROM wh__sales", "csv", dest)
    assert executed and executed[0].startswith("SELECT * FROM sales")
    assert "LIMIT" in executed[0]
    assert dest.exists()


def test_snapshot_pushes_aggregation_not_raw_extract(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake([("north", 3), ("south", 1)], executed)
    )
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        eng.snapshot_sync("SELECT region, count(*) AS n FROM wh__sales GROUP BY region", "snap")
        result = eng.query_sync("SELECT region, n FROM local.snap ORDER BY region")
    assert executed == ["SELECT region, count(*) AS n FROM sales GROUP BY region"]
    assert result.rows == [("north", 3), ("south", 1)]


def test_snapshot_falls_back_to_raw_extract_when_not_pushable(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake([(1, "north"), (2, "south")], executed)
    )
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        eng.snapshot_sync("SELECT * FROM wh__sales", "snap")
        result = eng.query_sync("SELECT count(*) AS c FROM local.snap")
    assert executed and executed[0].startswith("SELECT * FROM sales")
    assert "LIMIT" in executed[0]
    assert result.rows == [(2,)]


# A pushed aggregate column can hold both int (integral) and float (fractional)
# values — _coerce collapses Decimals that way. The staging table must widen to
# DOUBLE so fractional values are not silently truncated to a BIGINT first guess.
_MIXED = "SELECT region, sum(amount) AS s FROM wh__sales GROUP BY region"
_MIXED_REMOTE = "SELECT region, sum(amount) AS s FROM sales GROUP BY region"


def test_export_preserves_fractional_in_mixed_numeric_column(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake([("a", 100), ("b", 100.5)], executed)
    )
    dest = tmp_path / "out.csv"
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        eng.export_sync(_MIXED, "csv", dest)
    assert executed == [_MIXED_REMOTE]
    back = duckdb.connect().execute(f"SELECT s FROM read_csv_auto('{dest}')").fetchall()
    assert (100.5,) in back  # fractional value survived, not truncated to 100


def test_snapshot_preserves_fractional_in_mixed_numeric_column(tmp_path, monkeypatch):
    from datacharter.engine import snowflake as sf_mod

    executed: list[str] = []
    monkeypatch.setattr(
        sf_mod, "_connect", lambda _s: _FakeSnowflake([("a", 100), ("b", 100.5)], executed)
    )
    with Engine(tmp_path, [_snowflake_source()]) as eng:
        eng.snapshot_sync(_MIXED, "snap")
        result = eng.query_sync("SELECT s FROM local.snap ORDER BY region")
    assert executed == [_MIXED_REMOTE]
    assert result.rows == [(100.0,), (100.5,)]  # both preserved as DOUBLE
