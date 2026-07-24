"""Deterministic filter/projection pushdown extraction (D11) — no agent."""

import duckdb
import pytest

from datacharter.engine.pushdown import Pushdown, extract_pushdown

CONNECTORS = {"wh__users"}


@pytest.fixture
def conn():
    c = duckdb.connect()
    yield c
    c.close()


def _one(conn, sql, connectors=CONNECTORS):
    return extract_pushdown(conn, sql, connectors)


def test_single_table_filter_and_projection(conn):
    pd = _one(conn, "SELECT email, tier FROM wh__users WHERE tier='pro'")["wh__users"]
    assert pd.columns == {"email", "tier"}
    assert pd.predicates == ["tier = 'pro'"]


def test_numeric_and_in_and_isnull_and_like(conn):
    pd = _one(
        conn,
        "SELECT id FROM wh__users "
        "WHERE age >= 30 AND region IN ('us','eu') AND note IS NULL AND name LIKE 'a%'",
    )["wh__users"]
    assert pd.predicates == [
        "age >= 30",
        "region IN ('us', 'eu')",
        "note IS NULL",
        "name LIKE 'a%'",
    ]


def test_qualified_columns_via_alias(conn):
    pd = _one(conn, "SELECT u.email FROM wh__users u WHERE u.tier='pro'")["wh__users"]
    assert pd.columns == {"email", "tier"}
    assert pd.predicates == ["tier = 'pro'"]


def test_cross_source_pushes_only_connector_leg(conn):
    # Only the connector-table predicate pushes; join cond + other leg do not.
    result = _one(
        conn,
        "SELECT u.email, o.total FROM wh__users u "
        "JOIN pg__orders o ON o.uid = u.id "
        "WHERE u.tier='pro' AND o.total > 100",
        {"wh__users"},
    )
    pd = result["wh__users"]
    assert pd.predicates == ["tier = 'pro'"]  # not o.total, not the join
    # email (selected) + id (join key) + tier (WHERE col, re-filtered locally).
    assert pd.columns == {"email", "id", "tier"}


def test_unqualified_column_in_multitable_is_not_attributed(conn):
    # `x` is ambiguous across two tables -> no predicate pushed, full columns.
    result = _one(
        conn,
        "SELECT wh__users.email FROM wh__users JOIN pg__o ON pg__o.id = wh__users.id WHERE x = 1",
        {"wh__users"},
    )
    pd = result["wh__users"]
    assert pd.predicates == []
    assert pd.columns is None


def test_star_forces_full_projection(conn):
    pd = _one(conn, "SELECT * FROM wh__users WHERE tier='pro'")["wh__users"]
    assert pd.columns is None
    assert pd.predicates == ["tier = 'pro'"]


def test_function_predicate_not_pushed_but_column_projected(conn):
    pd = _one(conn, "SELECT id FROM wh__users WHERE upper(name) = 'X'")["wh__users"]
    assert pd.predicates == []  # function-wrapped predicate stays local
    assert pd.columns == {"id", "name"}  # name still needed to filter locally


def test_or_predicate_not_pushed(conn):
    pd = _one(conn, "SELECT id FROM wh__users WHERE tier='pro' OR tier='free'")["wh__users"]
    assert pd.predicates == []


def test_self_join_is_poisoned(conn):
    result = _one(
        conn,
        "SELECT a.id FROM wh__users a JOIN wh__users b ON b.mgr = a.id WHERE a.tier='pro'",
        {"wh__users"},
    )
    pd = result["wh__users"]
    assert pd.columns is None and pd.predicates == []


def test_unreferenced_connector_absent(conn):
    assert _one(conn, "SELECT 1 FROM pg__orders") == {}


def test_unparseable_falls_back_to_full_extract(conn):
    # A non-serializable / non-select statement still materializes named tables.
    result = extract_pushdown(conn, "DESCRIBE wh__users", CONNECTORS)
    assert result == {"wh__users": Pushdown()}
    assert result["wh__users"].columns is None


def test_string_literal_is_escaped(conn):
    pd = _one(conn, "SELECT id FROM wh__users WHERE name = 'O''Brien'")["wh__users"]
    assert pd.predicates == ["name = 'O''Brien'"]


def test_backslash_injection_escaped(conn):
    # A value ending in a backslash must not escape the closing quote on
    # Snowflake (DC-SEC-005): the backslash is doubled.
    bs = chr(92)
    pd = _one(conn, "SELECT id FROM wh__users WHERE name = 'x" + bs + "'")["wh__users"]
    assert pd.predicates[0].count(bs) == 2
    injected = _one(conn, "SELECT id FROM wh__users WHERE name = 'a'' OR 1=1'")["wh__users"]
    assert injected.predicates == ["name = 'a'' OR 1=1'"]


def test_select_sql_render():
    assert (
        Pushdown(columns={"email", "id"}, predicates=["tier = 'pro'"]).select_sql("users", 100)
        == "SELECT email, id FROM users WHERE tier = 'pro' LIMIT 100"
    )
    assert Pushdown().select_sql("users", 50) == "SELECT * FROM users LIMIT 50"
