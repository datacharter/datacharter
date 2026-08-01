"""Policy guard: co-occurrence, aggregate certification, k-anonymity rewrite."""

import duckdb
import pytest

from datacharter.contracts.policies import Policy
from datacharter.engine.policy_guard import PolicyRefusal, apply_min_group, check_policies

AGG_ONLY = {"customers": Policy(aggregate_only=True)}
K10 = {"customers": Policy(aggregate_only=True, min_group_size=10)}


def test_untouched_relations_pass():
    assert check_policies("SELECT * FROM orders", AGG_ONLY) is None


def test_plain_select_on_policied_refused():
    with pytest.raises(PolicyRefusal, match="aggregates only"):
        check_policies("SELECT email FROM customers", AGG_ONLY)


def test_distinct_refused():
    with pytest.raises(PolicyRefusal, match="aggregates only"):
        check_policies("SELECT DISTINCT region FROM customers", AGG_ONLY)


def test_groupby_aggregate_passes_and_returns_k():
    k = check_policies("SELECT region, count(*) FROM customers GROUP BY region", K10)
    assert k == 10


def test_global_aggregate_passes():
    assert check_policies("SELECT count(*), avg(age) FROM customers", AGG_ONLY) is None


def test_window_function_refused():
    with pytest.raises(PolicyRefusal):
        check_policies("SELECT sum(age) OVER () FROM customers", AGG_ONLY)


def test_cte_refused_fail_closed():
    with pytest.raises(PolicyRefusal):
        check_policies(
            "WITH c AS (SELECT * FROM customers) SELECT count(*) FROM c", AGG_ONLY
        )


def test_union_row_egress_refused():
    with pytest.raises(PolicyRefusal):
        check_policies(
            "SELECT region FROM customers UNION ALL SELECT region FROM customers",
            AGG_ONLY,
        )


def test_no_joins_cooccurrence():
    pols = {"customers": Policy(no_joins=True)}
    with pytest.raises(PolicyRefusal, match="queried together"):
        check_policies("SELECT count(*) FROM customers c JOIN orders o ON true", pols)
    assert check_policies("SELECT count(*) FROM customers", pols) is None


def test_no_joins_to_specific():
    pols = {"customers": Policy(no_joins_to={"payments"})}
    with pytest.raises(PolicyRefusal, match="payments"):
        check_policies("SELECT count(*) FROM customers, payments", pols)
    assert check_policies("SELECT count(*) FROM customers, orders", pols) is None


def test_qualified_relation_matching():
    k = check_policies(
        "SELECT region, count(*) FROM crm.customers GROUP BY region",
        {"crm.customers": Policy(min_group_size=5)},
    )
    assert k == 5


def test_strictest_k_wins():
    pols = {
        "customers": Policy(min_group_size=10),
        "orders": Policy(min_group_size=25),
    }
    k = check_policies(
        "SELECT count(*) FROM customers, orders", pols
    )
    assert k == 25


def test_apply_min_group_suppresses_small_groups():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE customers AS SELECT * FROM (VALUES "
                "('US'),('US'),('US'),('EU'),('EU'),('ZZ')) t(region)")
    sql = "SELECT region, count(*) AS n FROM customers GROUP BY region"
    rewritten = apply_min_group(sql, 2)
    rows = con.execute(rewritten).fetchall()
    regions = {r[0] for r in rows}
    assert regions == {"US", "EU"}          # ZZ (1 row) suppressed
    assert all(len(r) == 2 for r in rows)   # helper column EXCLUDEd
    con.close()


def test_apply_min_group_global_aggregate():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE t AS SELECT 1 x")
    assert con.execute(apply_min_group("SELECT sum(x) FROM t", 5)).fetchall() == []
    con.execute("INSERT INTO t SELECT 1 FROM range(10)")
    assert con.execute(apply_min_group("SELECT sum(x) FROM t", 5)).fetchall() != []
    con.close()
