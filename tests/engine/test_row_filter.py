"""apply_row_filters wraps referenced filtered tables; fail-closed on rewrite failure."""

import duckdb
import pytest

from datacharter.engine.row_filter import RowFilterError, apply_row_filters

FILTERS = {"t": "region = 'us'"}


def _run(sql):
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES (1,'us'),(2,'eu'),(3,'us')) v(a,region)")
    return con.execute(apply_row_filters(sql, FILTERS)).fetchall()


def test_bare_select_is_filtered():
    assert sorted(r[0] for r in _run("SELECT a FROM t")) == [1, 3]


def test_aliased_and_predicate_preserved():
    assert sorted(r[0] for r in _run("SELECT c.a FROM t c WHERE c.a >= 1")) == [1, 3]


def test_aggregate_counts_filtered_rows():
    assert _run("SELECT count(*) AS n FROM t") == [(2,)]


def test_unfiltered_query_is_unchanged():
    assert apply_row_filters("SELECT 1 AS x", FILTERS) == "SELECT 1 AS x"


def test_untouched_table_not_wrapped():
    assert apply_row_filters("SELECT 1 FROM other", FILTERS) == "SELECT 1 FROM other"


def test_malformed_predicate_on_referenced_table_fails_closed():
    with pytest.raises(RowFilterError):
        apply_row_filters("SELECT a FROM t", {"t": "this is ) not sql"})
