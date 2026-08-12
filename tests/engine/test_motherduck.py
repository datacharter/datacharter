"""MotherDuck source: a governed ATTACH-with-secret over DuckDB-in-the-cloud.

The SQL-shape tests are deterministic. The end-to-end test needs a real
`MOTHERDUCK_TOKEN` (I can't create the account), so it's skipped otherwise — set
the env var to exercise it against live MotherDuck."""

import os

import pytest

from datacharter.contracts import load_charter
from datacharter.engine.session import Engine
from datacharter.engine.sources import SourceConfigError, qualified_name, registration_sql
from datacharter.models import ATTACH_TYPES, COMMUNITY_ATTACH_EXTENSIONS, Source, SourceType


def _src(**kw):
    kw.setdefault("name", "md")
    kw.setdefault("type", SourceType.MOTHERDUCK)
    kw.setdefault("connection", {"database": "analytics"})
    kw.setdefault("credentials", {"token": "tok-123"})
    return Source(**kw)


def test_motherduck_is_attach_type_not_community_extension():
    assert SourceType.MOTHERDUCK in ATTACH_TYPES
    # signed extension, not a community one → must not get `INSTALL ... FROM community`
    assert SourceType.MOTHERDUCK not in COMMUNITY_ATTACH_EXTENSIONS


def test_motherduck_registration_sql(tmp_path):
    stmts = registration_sql(_src(), tmp_path)
    assert stmts == [
        "INSTALL motherduck",
        "LOAD motherduck",
        "SET motherduck_token = 'tok-123'",
        "ATTACH 'md:analytics' AS md (TYPE motherduck, READ_ONLY)",
    ]
    # the token is set via SET, never in the ATTACH string
    assert "tok-123" not in stmts[-1]
    assert "READ_ONLY" in stmts[-1]


def test_motherduck_registration_without_database(tmp_path):
    stmts = registration_sql(_src(connection={}), tmp_path)
    assert stmts[-1] == "ATTACH 'md:' AS md (TYPE motherduck, READ_ONLY)"


def test_motherduck_missing_token_errors(tmp_path):
    with pytest.raises(SourceConfigError, match="needs a token"):
        registration_sql(_src(credentials={}), tmp_path)


def test_motherduck_qualified_name_defaults_to_main():
    assert qualified_name(_src(), "customers") == "md.main.customers"
    s = _src(connection={"database": "analytics", "schema": "mart"})
    assert qualified_name(s, "orders") == "md.mart.orders"


def test_charter_with_motherduck_source_loads(tmp_path):
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  warehouse:\n"
        "    type: motherduck\n"
        "    connection:\n"
        "      database: analytics\n"
        "    credentials:\n"
        "      token: ${MOTHERDUCK_TOKEN}\n"
        "    tables: [customers, orders]\n"
        "    pii:\n"
        "      customers: [email]\n"
    )
    charter = load_charter(tmp_path, lenient_secrets=True)
    src = charter.sources[0]
    assert src.type == SourceType.MOTHERDUCK
    assert src.tables == ["customers", "orders"]
    assert src.pii == {"customers": ["email"]}


@pytest.mark.skipif(
    not os.environ.get("MOTHERDUCK_TOKEN"),
    reason="set MOTHERDUCK_TOKEN to run the live MotherDuck attach/query",
)
def test_motherduck_end_to_end(tmp_path):
    db = os.environ.get("MOTHERDUCK_TEST_DB", "sample_data")
    src = Source(
        name="md", type=SourceType.MOTHERDUCK,
        connection={"database": db},
        credentials={"token": os.environ["MOTHERDUCK_TOKEN"]},
    )
    with Engine(tmp_path, [src]) as eng:
        assert eng.query_sync("SELECT 1 AS ok").rows[0][0] == 1
