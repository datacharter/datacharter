import json

import pytest
from fastapi.testclient import TestClient

from datacharter.agent.tools import ToolBox
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.provenance import extract_provenance
from datacharter.engine.session import Engine
from datacharter.server import create_app


def test_single_table_attributes_unqualified_columns():
    prov = extract_provenance("SELECT email, tier FROM customers WHERE tier = 'pro'")
    assert prov["relations"] == ["customers"]
    assert prov["columns"] == ["customers.email", "customers.tier"]


def test_join_resolves_aliases_to_relations():
    prov = extract_provenance(
        "SELECT c.email, o.total FROM crm.customers c JOIN main.orders o ON o.cid = c.id"
    )
    assert prov["relations"] == ["crm.customers", "main.orders"]
    assert "crm.customers.email" in prov["columns"]
    assert "main.orders.total" in prov["columns"]


def test_no_tables_returns_none():
    assert extract_provenance("SELECT 1 AS x") is None


def test_star_reports_relation_without_columns():
    prov = extract_provenance("SELECT * FROM customers")
    assert prov["relations"] == ["customers"]
    assert prov["columns"] == []


def test_non_select_returns_none():
    assert extract_provenance("DROP TABLE local.x") is None


def test_lineage_maps_output_to_input_columns():
    prov = extract_provenance(
        "SELECT c.email AS mail, upper(c.tier) AS t, count(*) AS n "
        "FROM crm.customers c GROUP BY 1, 2"
    )
    assert prov["lineage"]["mail"] == ["crm.customers.email"]
    assert prov["lineage"]["t"] == ["crm.customers.tier"]
    assert prov["lineage"]["n"] == []  # count(*) reads no named column


def test_lineage_passthrough_uses_column_name():
    prov = extract_provenance("SELECT email FROM customers")
    assert prov["lineage"]["email"] == ["customers.email"]


def test_star_has_no_lineage():
    prov = extract_provenance("SELECT * FROM customers")
    assert "lineage" not in prov  # cannot attribute * to specific outputs


@pytest.fixture
def engine(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield eng, charter.sources
    finally:
        eng.close()


def test_engine_attaches_provenance(engine):
    eng, _ = engine
    result = eng.query_sync("SELECT email FROM store.customers")
    assert result.provenance["relations"] == ["store.customers"]
    assert result.provenance["columns"] == ["store.customers.email"]


def test_ddl_has_no_provenance(engine):
    eng, _ = engine
    result = eng.query_sync("CREATE TABLE local.snap AS SELECT 1 AS a")
    assert result.provenance is None


async def test_agent_tool_result_includes_provenance(engine):
    eng, sources = engine
    box = ToolBox(eng, sources)
    payload = json.loads(
        await box.run("query", json.dumps({"sql": "SELECT tier FROM store.customers"}))
    )
    assert payload["provenance"]["relations"] == ["store.customers"]


def test_api_query_returns_provenance(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        body = c.post("/api/query", json={"sql": "SELECT tier FROM store.customers"}).json()
    assert body["provenance"]["relations"] == ["store.customers"]
