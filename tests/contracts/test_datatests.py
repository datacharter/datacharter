"""check_sql compiles each assertion to a failing-row count; validation is strict."""

import duckdb
import pytest

from datacharter.contracts.datatests import DataTest, DataTestError, check_sql


def _con():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t AS SELECT * FROM (VALUES "
        "(1,'US',10),(2,'EU',20),(2,NULL,-5)) v(id,region,total)"
    )
    return con


def _fail(con, test) -> int:
    return con.execute(check_sql(test)).fetchone()[0]


def test_not_null():
    con = _con()
    assert _fail(con, DataTest(name="a", type="not_null", relation="t", column="id")) == 0
    assert _fail(con, DataTest(name="a", type="not_null", relation="t", column="region")) == 1


def test_unique():
    con = _con()
    assert _fail(con, DataTest(name="a", type="unique", relation="t", columns=["id"])) == 1
    assert _fail(con, DataTest(name="a", type="unique", relation="t", columns=["id", "total"])) == 0


def test_accepted_values_quotes_strings():
    con = _con()
    ok = DataTest(
        name="a", type="accepted_values", relation="t", column="region", values=["US", "EU"]
    )
    assert _fail(con, ok) == 0  # NULL ignored, US/EU allowed
    bad = DataTest(name="a", type="accepted_values", relation="t", column="region", values=["US"])
    assert _fail(con, bad) == 1  # EU not allowed


def test_expression():
    con = _con()
    t = DataTest(name="a", type="expression", relation="t", expression="total >= 0")
    assert _fail(con, t) == 1  # the -5 row


def test_row_count_bounds():
    con = _con()
    assert _fail(con, DataTest(name="a", type="row_count", relation="t", min=1)) == 0
    assert _fail(con, DataTest(name="a", type="row_count", relation="t", min=99)) == 1
    assert _fail(con, DataTest(name="a", type="row_count", relation="t", max=1)) == 1


def test_validation_errors():
    with pytest.raises(DataTestError):
        check_sql(DataTest(name="a", type="bogus", relation="t"))
    with pytest.raises(DataTestError):
        check_sql(DataTest(name="a", type="not_null", relation="t"))  # missing column
    with pytest.raises(DataTestError):
        check_sql(DataTest(name="a", type="not_null", relation="t; DROP TABLE x", column="id"))
