"""Snowflake NUMBER/FIXED maps to an exact DuckDB type from precision/scale."""

from decimal import Decimal

import duckdb

from datacharter.engine.snowflake import _duckdb_type, materialize_snowflake
from datacharter.models import Source, SourceType


def _desc(name, type_code, precision=None, scale=None):
    return (name, type_code, None, None, precision, scale, None)


def test_duckdb_type_mapping():
    assert _duckdb_type(_desc("id", 0, 38, 0)) == "HUGEINT"
    assert _duckdb_type(_desc("n", 0, 9, 0)) == "BIGINT"
    assert _duckdb_type(_desc("amt", 0, 10, 2)) == "DECIMAL(10,2)"
    assert _duckdb_type(_desc("u", 0, None, None)) == "HUGEINT"
    assert _duckdb_type(_desc("r", 1)) == "DOUBLE"  # REAL/FLOAT
    assert _duckdb_type(_desc("t", 2)) == "VARCHAR"  # TEXT


class _FakeCursor:
    def __init__(self, rows, description):
        self._rows, self.description, self.executed = rows, description, None

    def execute(self, sql):
        self.executed = sql

    def fetchmany(self, n):
        batch, self._rows = self._rows[:n], self._rows[n:]
        return batch

    def close(self):
        pass


class _FakeSnowflake:
    def __init__(self, rows, description):
        self._rows, self._description = rows, description

    def cursor(self):
        return _FakeCursor(list(self._rows), self._description)

    def close(self):
        pass


def _materialize(desc, rows):
    src = Source(name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"}, tables=["t"])
    conn = duckdb.connect()
    fake = _FakeSnowflake(rows=rows, description=desc)
    materialize_snowflake(conn, src, ["t"], connector=fake)
    return conn


def test_extract_preserves_big_integer():
    conn = _materialize([_desc("id", 0, 38, 0)], [(Decimal("99999999999999999999"),)])
    (val,) = conn.execute('SELECT id FROM "wh__t"').fetchone()
    assert str(val) == "99999999999999999999"  # exact, not 1e20


def test_extract_preserves_2pow53_plus_one():
    big = 2**53 + 1
    conn = _materialize([_desc("id", 0, 18, 0)], [(big,)])
    (val,) = conn.execute('SELECT id FROM "wh__t"').fetchone()
    assert int(val) == big  # low bit intact


def test_extract_preserves_exact_decimal():
    conn = _materialize([_desc("amt", 0, 10, 2)], [(Decimal("12345.67"),)])
    (val,) = conn.execute('SELECT amt FROM "wh__t"').fetchone()
    assert Decimal(str(val)) == Decimal("12345.67")
