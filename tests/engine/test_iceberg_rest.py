"""Iceberg REST catalog source (Polaris / Nessie / Lakekeeper / Unity / Glue /
S3 Tables), governed and attached READ_ONLY via the core `iceberg` extension.

SQL-shape tests are deterministic; the ATTACH/SECRET syntax is verified against the
real extension in-session. A live attach+query needs a running REST catalog + token,
so it's marked and skipped unless the env is set."""

import os

import pytest

from datacharter.contracts import load_charter
from datacharter.engine.sources import SourceConfigError, qualified_name, registration_sql
from datacharter.models import ATTACH_TYPES, COMMUNITY_ATTACH_EXTENSIONS, Source, SourceType


def _src(**kw):
    kw.setdefault("name", "lake")
    kw.setdefault("type", SourceType.ICEBERG_REST)
    return Source(**kw)


def test_iceberg_rest_is_attach_type_not_community_extension():
    assert SourceType.ICEBERG_REST in ATTACH_TYPES
    assert SourceType.ICEBERG_REST not in COMMUNITY_ATTACH_EXTENSIONS


def test_oauth2_rest_registration(tmp_path):
    s = _src(
        connection={"warehouse": "wh", "endpoint": "https://cat/rest",
                    "oauth2_server_uri": "https://cat/oauth/tokens"},
        credentials={"client_id": "cid", "client_secret": "csec"},
    )
    stmts = registration_sql(s, tmp_path)
    assert stmts[:2] == ["INSTALL iceberg", "LOAD iceberg"]
    assert stmts[2] == (
        "CREATE OR REPLACE TEMPORARY SECRET lake_ice "
        "(TYPE iceberg, CLIENT_ID 'cid', CLIENT_SECRET 'csec', "
        "OAUTH2_SERVER_URI 'https://cat/oauth/tokens')"
    )
    assert stmts[3] == "ATTACH 'wh' AS lake (TYPE iceberg, ENDPOINT 'https://cat/rest', READ_ONLY)"
    assert "csec" not in stmts[3]  # secret stays out of the ATTACH string


def test_token_registration(tmp_path):
    s = _src(connection={"warehouse": "wh", "endpoint": "https://cat"}, credentials={"token": "bt"})
    stmts = registration_sql(s, tmp_path)
    assert stmts[2] == "CREATE OR REPLACE TEMPORARY SECRET lake_ice (TYPE iceberg, TOKEN 'bt')"
    assert stmts[3] == "ATTACH 'wh' AS lake (TYPE iceberg, ENDPOINT 'https://cat', READ_ONLY)"


def test_glue_registration_uses_endpoint_type(tmp_path):
    s = _src(
        connection={"warehouse": "123456789012", "endpoint_type": "GLUE"},
        credentials={"key_id": "AK", "secret": "SK", "region": "us-east-1"},
    )
    stmts = registration_sql(s, tmp_path)
    assert "KEY_ID 'AK'" in stmts[2] and "REGION 'us-east-1'" in stmts[2]
    assert stmts[3] == (
        "ATTACH '123456789012' AS lake (TYPE iceberg, ENDPOINT_TYPE 'GLUE', READ_ONLY)"
    )


def test_authorization_type_none_for_dev_catalog(tmp_path):
    s = _src(connection={"warehouse": "wh", "endpoint": "http://localhost:8181",
                         "authorization_type": "none"})
    stmts = registration_sql(s, tmp_path)
    assert stmts[-1] == (
        "ATTACH 'wh' AS lake (TYPE iceberg, ENDPOINT 'http://localhost:8181', "
        "AUTHORIZATION_TYPE 'none', READ_ONLY)"
    )
    # no creds -> no secret statement, just INSTALL/LOAD/ATTACH
    assert not any("SECRET" in x for x in stmts)


def test_missing_warehouse_and_endpoint_error(tmp_path):
    with pytest.raises(SourceConfigError, match="warehouse"):
        registration_sql(_src(connection={"endpoint": "https://c"}), tmp_path)
    with pytest.raises(SourceConfigError, match="endpoint"):
        registration_sql(_src(connection={"warehouse": "wh"}), tmp_path)


def test_qualified_name_uses_namespace():
    s = _src(connection={"warehouse": "wh", "endpoint": "https://c"})
    assert qualified_name(s, "orders") == "lake.default.orders"
    s2 = _src(connection={"warehouse": "wh", "endpoint": "https://c", "namespace": "analytics"})
    assert qualified_name(s2, "orders") == "lake.analytics.orders"


def test_charter_with_iceberg_rest_loads(tmp_path):
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  lake:\n"
        "    type: iceberg_rest\n"
        "    connection:\n"
        "      warehouse: my_wh\n"
        "      endpoint: https://catalog/rest\n"
        "      namespace: analytics\n"
        "    credentials:\n"
        "      token: ${ICEBERG_TOKEN}\n"
        "    tables: [customers, orders]\n"
        "    pii:\n"
        "      customers: [email]\n"
    )
    charter = load_charter(tmp_path, lenient_secrets=True)
    src = charter.sources[0]
    assert src.type == SourceType.ICEBERG_REST
    assert src.connection["warehouse"] == "my_wh"
    assert src.pii == {"customers": ["email"]}


@pytest.mark.skipif(
    not (os.environ.get("ICEBERG_REST_ENDPOINT") and os.environ.get("ICEBERG_REST_TOKEN")),
    reason="set ICEBERG_REST_ENDPOINT + ICEBERG_REST_TOKEN (+ _WAREHOUSE) for the live attach",
)
def test_iceberg_rest_end_to_end(tmp_path):
    from datacharter.engine.session import Engine

    src = Source(
        name="lake", type=SourceType.ICEBERG_REST,
        connection={"warehouse": os.environ.get("ICEBERG_REST_WAREHOUSE", "warehouse"),
                    "endpoint": os.environ["ICEBERG_REST_ENDPOINT"]},
        credentials={"token": os.environ["ICEBERG_REST_TOKEN"]},
    )
    with Engine(tmp_path, [src]) as eng:
        assert eng.query_sync("SELECT 1 AS ok").rows[0][0] == 1
