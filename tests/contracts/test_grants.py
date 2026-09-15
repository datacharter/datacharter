"""principals: and grants: in charter.yaml. Identities in git, default-deny."""

from datacharter.contracts import load_charter
from datacharter.contracts.grants import CharterPolicy, PrincipalRef
from datacharter.mcp.auth import Principal


def _ws(tmp_path, extra: str) -> None:
    (tmp_path / "d.csv").write_text("id,email\n1,a@b.com\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  store:\n"
        "    type: csv\n"
        "    path: d.csv\n"
        f"{extra}"
    )


def test_load_parses_principals_and_grants(tmp_path):
    _ws(
        tmp_path,
        "principals:\n"
        "  analyst: alice@corp\n"
        "  batch:\n"
        "    sub: svc-batch\n"
        "    roles: [etl]\n"
        "grants:\n"
        "  analyst:\n"
        "    - store.orders\n"
        "    - store.customers.tier\n"
        "  batch: [store.*]\n",
    )
    charter = load_charter(tmp_path)
    assert charter.principals["analyst"].sub == "alice@corp"
    assert charter.principals["batch"].sub == "svc-batch"
    assert charter.principals["batch"].roles == ("etl",)
    assert charter.grants["analyst"] == ["store.orders", "store.customers.tier"]
    assert charter.grants["batch"] == ["store.*"]


def test_access_roles_become_grants_when_grants_absent(tmp_path):
    _ws(tmp_path, "access:\n  roles:\n    analyst: [store.orders]\n")
    charter = load_charter(tmp_path)
    assert charter.grants["analyst"] == ["store.orders"]


def test_bad_grant_shape_is_a_load_error(tmp_path):
    from datacharter.contracts import CharterError

    _ws(tmp_path, "grants:\n  analyst: not-a-list\n")
    try:
        load_charter(tmp_path)
        raise AssertionError("expected CharterError")
    except CharterError as exc:
        assert "grants" in str(exc)


def test_charter_policy_table_and_column_and_wildcard():
    policy = CharterPolicy(
        principals={"analyst": PrincipalRef(sub="alice@corp")},
        grants={
            "analyst": ["store.orders", "store.customers.tier"],
            "etl": ["store.*"],
        },
    )
    alice = Principal(subject="alice@corp")
    assert policy.permits(alice, "store", "orders") is True
    assert policy.permits(alice, "store", "orders", "amount") is True
    assert policy.permits(alice, "store", "customers") is True
    assert policy.permits(alice, "store", "customers", "tier") is True
    assert policy.permits(alice, "store", "customers", "email") is False
    assert policy.permits(alice, "hr") is False
    unknown = Principal(subject="nobody")
    assert policy.permits(unknown, "store", "orders") is False
    etl = Principal(subject="x", claims={"roles": ["etl"]})
    assert policy.permits(etl, "store", "customers", "email") is True
