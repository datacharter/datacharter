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


def test_local_llm_detection_lists_running_runtimes(demo_client, monkeypatch):
    # The connect dialog lists models from locally-running runtimes; probing is
    # loopback-only with silent failures, so absent runtimes just don't appear.
    from datacharter.server import llm_admin

    async def fake_detect():
        return [
            {"provider": "ollama", "base_url": "http://127.0.0.1:11434/v1",
             "models": ["qwen3:8b", "llama3.2:3b"]}
        ]

    monkeypatch.setattr(llm_admin, "detect_local_llms", fake_detect)
    c, _ = demo_client
    body = c.get("/api/llm/local").json()
    assert body["runtimes"][0]["provider"] == "ollama"
    assert "qwen3:8b" in body["runtimes"][0]["models"]


def test_local_llm_detection_empty_when_nothing_runs(demo_client, monkeypatch):
    from datacharter.server import llm_admin

    async def fake_detect():
        return []

    monkeypatch.setattr(llm_admin, "detect_local_llms", fake_detect)
    c, _ = demo_client
    assert c.get("/api/llm/local").json() == {"runtimes": []}


def test_configuring_an_llm_switches_the_backend(demo_client):
    # The dead-end: Claude Code connected, user configures an LLM, backend
    # silently stayed claude-code with no way back.
    from datacharter.server import agent_backend

    c, ws = demo_client
    agent_backend.set_backend(ws, "claude-code")
    r = c.post("/api/agent/config", json={"base_url": "http://127.0.0.1:11434/v1",
                                          "model": "qwen2.5:7b"})
    assert r.status_code == 200 and r.json()["backend"] == "llm"
    assert agent_backend.get_backend(ws) == "llm"


def test_disconnect_backend_and_ask_refuses_cleanly(demo_client):
    from datacharter.server import agent_backend

    c, ws = demo_client
    assert c.post("/api/agent/backend", json={"backend": "none"}).status_code == 200
    assert agent_backend.get_backend(ws) == "none"
    assert c.get("/api/agent/available").json()["backend"] == "none"
    r = c.post("/api/agent/ask", json={"question": "hi"})
    assert "No agent connected" in r.text


def test_uploaded_file_pii_is_auto_masked_and_toggleable(demo_client):
    # A dragged file with an obvious PII column must not reach the agent
    # unmasked (startup detection never saw it), and its toggles must persist
    # via local_access and enforce on the agent surface.
    c, _ = demo_client
    csv = b"person_name,contact_email\nada,ada@real.com\n"
    r = c.post("/api/upload", files={"file": ("people2.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["table"] == "people2"

    def access():
        t = [t for t in c.get("/api/tables").json()["tables"] if t["table"] == "people2"][0]
        return {k: v["masked"] for k, v in t["access"].items()}

    assert access()["contact_email"] is True  # auto-detected post-upload
    out = c.post(
        "/api/tool",
        json={"name": "query",
              "arguments": '{"sql": "SELECT contact_email FROM people2 LIMIT 1"}'},
    ).json()["result"]
    assert "ada@real.com" not in out

    # toggle the whole upload real via the tree's path (source="local")
    assert c.post(
        "/api/agent-access", json={"source": "local", "table": "people2", "value": True}
    ).status_code == 200
    assert access() == {"person_name": False, "contact_email": False}
    out = c.post(
        "/api/tool",
        json={"name": "query",
              "arguments": '{"sql": "SELECT contact_email FROM people2 LIMIT 1"}'},
    ).json()["result"]
    assert "ada@real.com" in out
