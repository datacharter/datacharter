"""Interop with the Open Data Contract Standard (ODCS): import a contract into a
charter, export a charter as a contract, and round-trip."""

import json

import pytest

from datacharter.contracts import load_charter
from datacharter.contracts.odcs import export_odcs, import_odcs, import_odcs_file

_CONTRACT = {
    "apiVersion": "v3.0.0", "kind": "DataContract", "id": "crm", "name": "crm",
    "version": "1.0.0", "status": "active",
    "servers": [{"server": "prod", "type": "postgres", "host": "db.x",
                 "database": "analytics", "schema": "public"}],
    "schema": [
        {"name": "customers", "description": "one per customer", "properties": [
            {"name": "id", "logicalType": "integer"},
            {"name": "email", "logicalType": "string", "classification": "PII"},
            {"name": "phone", "logicalType": "string", "tags": ["pii"]},
        ]},
        {"name": "orders", "properties": [{"name": "id", "logicalType": "integer"}]},
    ],
}


def test_import_maps_server_tables_and_pii():
    charter, summary = import_odcs(_CONTRACT)
    src = charter["sources"]["crm"]
    assert src["type"] == "postgres"
    assert src["connection"]["host"] == "db.x" and src["connection"]["database"] == "analytics"
    assert src["tables"] == ["customers", "orders"]
    assert src["pii"]["customers"] == ["email", "phone"]  # classification + tags both caught
    assert src["context"]["customers"] == "one per customer"
    assert summary == {"source_type": "postgres", "source": "crm", "tables": 2,
                       "pii_columns": 2, "unmapped_type": False}


@pytest.mark.parametrize("odcs_type,expected", [
    ("snowflake", "snowflake"), ("bigquery", "bigquery"), ("sqlserver", "mssql"),
    ("databricks", "iceberg_rest"), ("weird-warehouse", "postgres"),
])
def test_server_type_mapping(odcs_type, expected):
    doc = {"servers": [{"type": odcs_type}], "schema": [{"name": "t", "properties": []}]}
    charter, summary = import_odcs(doc)
    assert next(iter(charter["sources"].values()))["type"] == expected
    assert summary["unmapped_type"] is (odcs_type == "weird-warehouse")


def test_export_charter_to_odcs(tmp_path):
    (tmp_path / "d.csv").write_text("id,email\n1,a@b.com\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  crm:\n    type: postgres\n"
        "    connection:\n      host: db.x\n      database: analytics\n"
        "    credentials:\n      password: ${DB_PASSWORD}\n"
        "    tables: [customers, orders]\n    pii:\n      customers: [email]\n"
    )
    charter = load_charter(tmp_path, lenient_secrets=True)
    odcs = export_odcs(charter)
    assert odcs["kind"] == "DataContract" and odcs["apiVersion"] == "v3.0.0"
    assert odcs["servers"][0]["type"] == "postgres" and odcs["servers"][0]["host"] == "db.x"
    customers = next(s for s in odcs["schema"] if s["name"] == "customers")
    assert customers["physicalName"] == "crm.customers"
    assert customers["properties"] == [{"name": "email", "logicalType": "string",
                                        "classification": "PII"}]


def test_round_trip_preserves_tables_and_pii(tmp_path):
    charter_text, _ = import_odcs_file(str(_write(tmp_path, _CONTRACT)))
    (tmp_path / "charter.yaml").write_text(charter_text)
    (tmp_path / "d.csv").write_text("x\n1\n")
    charter = load_charter(tmp_path, lenient_secrets=True)
    odcs = export_odcs(charter)
    names = {s["name"] for s in odcs["schema"]}
    assert {"customers", "orders"} <= names
    cust = next(s for s in odcs["schema"] if s["name"] == "customers")
    assert {p["name"] for p in cust["properties"]} == {"email", "phone"}


def _write(tmp_path, doc):
    p = tmp_path / "contract.json"
    p.write_text(json.dumps(doc))
    return p


def test_sqlite_source_uses_path_not_connection(tmp_path):
    doc = {
        "servers": [{"type": "sqlite", "path": "demo/store.db"}],
        "schema": [{"name": "customers", "properties": [
            {"name": "email", "classification": "PII"}]}],
    }
    charter, _ = import_odcs(doc)
    src = charter["sources"]["source"]
    assert src["type"] == "sqlite"
    assert src["path"] == "demo/store.db"  # path, not an unopenable host/user/password
    assert "connection" not in src


def test_sqlite_round_trips_path(tmp_path):
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  store:\n    type: sqlite\n    path: demo/store.db\n"
        "    tables: [customers]\n    pii:\n      customers: [email]\n")
    (tmp_path / "d.csv").write_text("x\n1\n")
    # sqlite path need not exist to load leniently for export.
    charter = load_charter(tmp_path, lenient_secrets=True)
    odcs = export_odcs(charter)
    assert odcs["servers"][0]["type"] == "sqlite"
    assert odcs["servers"][0]["path"] == "demo/store.db"


def test_cli_import_and_export(tmp_path):
    from datacharter.cli import main

    contract = _write(tmp_path, _CONTRACT)
    out = tmp_path / "charter.yaml"
    assert main(["import", "odcs", str(contract), "-o", str(out)]) == 0
    assert "customers" in out.read_text()
    # export it back
    (tmp_path / "d.csv").write_text("x\n1\n")
    odcs_out = tmp_path / "out.odcs.yaml"
    assert main(["export", "odcs", str(tmp_path), "-o", str(odcs_out)]) == 0
    assert "DataContract" in odcs_out.read_text()
