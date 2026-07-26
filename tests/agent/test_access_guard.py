"""The agent guard: a masked column may be SELECTed, never used to condition output."""

import pytest

from datacharter.agent.access_guard import AgentAccessDenied, check_query_access


# email is masked; everything else is real. Single demo-style source "store".
def _is_masked(source, table, column):
    return column.lower() == "email"


_MASKED_NAMES = {"email"}


def _check(sql):
    check_query_access(sql, is_masked=_is_masked, masked_names=_MASKED_NAMES)


# --- allowed ---
def test_masked_column_in_select_list_is_allowed():
    _check("SELECT email FROM store.customers")  # value masked downstream, not here


def test_select_star_is_allowed():
    _check("SELECT * FROM store.customers")


def test_expression_over_masked_in_select_list_is_allowed():
    _check("SELECT upper(email) AS c FROM store.customers")


def test_non_masked_column_in_where_is_allowed():
    _check("SELECT id FROM store.customers WHERE tier = 'gold'")


def test_non_masked_group_and_order_allowed():
    _check("SELECT tier, count(*) FROM store.customers GROUP BY tier ORDER BY tier")


# --- refused ---
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM store.customers WHERE email = 'ada@example.com'",
        "SELECT id FROM store.customers WHERE email LIKE 'a%'",
        "SELECT id FROM store.customers ORDER BY email LIMIT 1",
        "SELECT email, count(*) FROM store.customers GROUP BY email",
        "SELECT count(*) FROM store.customers HAVING max(email) > 'm'",
        "SELECT o.id FROM store.orders o JOIN store.customers c ON c.email = o.email",
        "SELECT id FROM store.customers WHERE id IN "
        "(SELECT id FROM store.customers WHERE email = 'x')",
    ],
)
def test_masked_column_in_conditioning_position_is_refused(sql):
    with pytest.raises(AgentAccessDenied):
        _check(sql)


def test_masked_column_in_subquery_projection_is_refused():
    # re-projecting a masked column through a subquery must not slip past
    with pytest.raises(AgentAccessDenied):
        _check("SELECT x FROM (SELECT email AS x FROM store.customers) t")


def test_failclosed_when_unparseable_and_masked_name_present():
    # not valid SQL json_serialize can tree-walk, but references a masked name
    with pytest.raises(AgentAccessDenied):
        check_query_access(
            "COPY store.customers (email) TO 'x'",
            is_masked=_is_masked,
            masked_names=_MASKED_NAMES,
        )


def test_unparseable_without_masked_name_is_allowed():
    check_query_access(
        "SELECT id FROM store.customers WHERE tier = 'gold'",
        is_masked=_is_masked,
        masked_names=set(),  # nothing to protect
    )
