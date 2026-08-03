"""The UI-parity endpoints: guides/evals CRUD, evidence export, recheck,
metrics, and data tests — everything the panels can now do must hold at the
API layer (validation, path safety, honest results)."""

import io
import sqlite3
import zipfile

import keyring
import keyring.backend
import pytest
from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.server import create_app


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, s, n):
        return self.store.get((s, n))

    def set_password(self, s, n, v):
        self.store[(s, n)] = v

    def delete_password(self, s, n):
        self.store.pop((s, n), None)


@pytest.fixture
def demo_client(tmp_path):
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    (tmp_path / "charter.yaml").write_text(
        (tmp_path / "charter.yaml").read_text()
        + "\ntests:\n"
        + "  customers_nonempty:\n"
        + "    relation: store.customers\n"
        + "    type: row_count\n"
        + "    min: 1\n"
        + "  customers_at_least_100:\n"
        + "    relation: store.customers\n"
        + "    type: row_count\n"
        + "    min: 100\n"
    )
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c, tmp_path
    keyring.set_keyring(prev)


def test_guide_create_and_delete_roundtrip(demo_client):
    c, ws = demo_client
    assert c.put("/api/guides", json={"name": "team", "content": "# notes"}).status_code == 200
    assert (ws / "guides" / "team.md").exists()
    assert c.delete("/api/guides/team").status_code == 200
    assert not (ws / "guides" / "team.md").exists()


def test_guide_delete_rejects_traversal_and_missing(demo_client):
    c, _ = demo_client
    assert c.delete("/api/guides/bad.name").status_code == 400  # dots rejected (no traversal)
    assert c.delete("/api/guides/nope").status_code == 404


def test_eval_suite_save_validates_like_the_runner(demo_client):
    c, ws = demo_client
    good = (
        'version: 1\ncases:\n  - question: "q?"\n    expect:\n'
        '      - { type: sql_contains, value: "orders" }\n'
    )
    r = c.put("/api/evals/files/weekly", json={"content": good})
    assert r.status_code == 200
    assert (ws / "evals" / "weekly.yaml").read_text() == good
    # the runner's own loader must accept what the endpoint accepted
    from datacharter.contracts.evals import load_suites

    assert any(s.name == "weekly" for s in load_suites(ws))


def test_eval_suite_save_rejects_broken_yaml_and_bad_assertions(demo_client):
    c, ws = demo_client
    r = c.put("/api/evals/files/bad", json={"content": "cases: ["})
    assert r.status_code == 400 and "YAML" in r.json()["error"]["message"]
    r = c.put(
        "/api/evals/files/bad",
        json={
            "content": "version: 1\ncases:\n  - question: q\n    expect:\n"
            "      - { type: nonsense }\n"
        },
    )
    assert r.status_code == 400 and "unknown assertion" in r.json()["error"]["message"]
    assert not (ws / "evals" / "bad.yaml").exists()  # invalid never lands on disk


def test_eval_suite_list_and_delete(demo_client):
    c, _ = demo_client
    c.put("/api/evals/files/tmp", json={"content": "version: 1\ncases: []\n"})
    names = [f["name"] for f in c.get("/api/evals/files").json()["files"]]
    assert "tmp" in names
    assert c.delete("/api/evals/files/tmp").status_code == 200
    assert c.delete("/api/evals/files/tmp").status_code == 404


def test_audit_export_returns_valid_evidence_zip(demo_client):
    c, _ = demo_client
    # produce at least one recorded access so the pack has content
    c.post("/api/tool", json={"name": "list_tables", "arguments": "{}"})
    r = c.post("/api/audit/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"entries.jsonl", "verification.txt"} <= set(z.namelist())


def test_snapshot_recheck_reports_unchanged_then_changed(demo_client):
    c, ws = demo_client
    sql = "SELECT count(*) AS n FROM store.customers"
    assert c.post("/api/snapshot", json={"name": "cust", "sql": sql}).status_code == 200
    r = c.post("/api/snapshot/cust/recheck").json()
    assert r["changed"] is False
    con = sqlite3.connect(ws / "demo" / "store.db")
    con.execute("INSERT INTO customers VALUES (4, 'new@example.com', 'free')")
    con.commit()
    con.close()
    r = c.post("/api/snapshot/cust/recheck").json()
    assert r["changed"] is True and r["new"] == 1
    assert c.post("/api/snapshot/nope/recheck").status_code == 404


def test_metrics_listing_compiles_sql(demo_client):
    c, _ = demo_client
    metrics = c.get("/api/metrics").json()["metrics"]
    rev = next(m for m in metrics if m["name"] == "revenue")
    assert "sum(total)" in rev["sql"] and rev["has_time"] is True


def test_data_tests_run_reports_pass_and_fail(demo_client):
    c, _ = demo_client
    body = c.post("/api/tests/run").json()
    by_name = {r["name"]: r for r in body["results"]}
    assert by_name["customers_nonempty"]["passed"] is True
    assert by_name["customers_at_least_100"]["passed"] is False
    assert body["passed"] is False
