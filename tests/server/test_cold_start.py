"""The cold-start journey a real adopter takes: `datacharter init` (empty, NO --demo)
-> serve -> run a query -> add your own source -> query it. This path was never
exercised (every other server test inits with --demo), which let two demo-only
assumptions ship — the loader rejecting empty `sources`, and the onboarding running a
hardcoded `store.orders` query. This guards the whole class at the integration level.
"""

import json
import sqlite3

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
def empty_client(tmp_path):
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    assert cli_main(["init", str(tmp_path)]) == 0  # NO --demo: a real empty workspace
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c, tmp_path
    keyring.set_keyring(prev)


def test_empty_workspace_serves_with_no_sources(empty_client):
    c, _ = empty_client
    assert c.get("/api/sources").json()["sources"] == []


def test_api_tool_governed_query_hits_demo_policy(empty_client):
    # the pristine demo now ships the tour's aggregates-only policy on customers:
    # a raw SELECT through the agent surface is refused, not masked.
    c, _ = empty_client
    c.post("/api/demo")
    r = c.post(
        "/api/tool",
        json={"name": "query", "arguments": '{"sql":"SELECT email FROM store.customers LIMIT 1"}'},
    )
    assert r.status_code == 200
    assert "policy" in r.json()["result"] and "@example.com" not in r.json()["result"]


def test_api_tool_masks_pii_on_unpolicied_table(empty_client):
    # masking still demonstrable: the canaries snapshot has masked PII and no policy.
    c, _ = empty_client
    c.post("/api/demo")
    r = c.post(
        "/api/tool",
        json={"name": "query", "arguments": '{"sql":"SELECT email FROM local.canaries LIMIT 1"}'},
    )
    assert r.status_code == 200
    data = json.loads(r.json()["result"])   # result is a JSON string from the governed toolbox
    assert data["rows"][0][0] == "•••"


def test_api_tool_lists_tables(empty_client):
    c, _ = empty_client
    c.post("/api/demo")
    r = c.post("/api/tool", json={"name": "list_tables", "arguments": "{}"})
    assert r.status_code == 200 and "orders" in r.json()["result"]


def test_query_works_on_empty_workspace(empty_client):
    # what the fixed first-run tutorial runs when there are no tables yet.
    c, _ = empty_client
    r = c.post("/api/query", json={"sql": "SELECT 42 AS answer"})
    assert r.status_code == 200 and r.json()["rows"] == [[42]]


def test_add_source_then_query_it(empty_client):
    c, ws = empty_client
    con = sqlite3.connect(ws / "crm.db")
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.execute("INSERT INTO accounts VALUES (1, 'acme')")
    con.commit()
    con.close()
    src = {"name": "crm", "type": "sqlite", "path": "crm.db", "tables": ["accounts"]}
    assert c.post("/api/sources", json=src).status_code == 200
    r = c.post("/api/query", json={"sql": "SELECT count(*) AS n FROM crm.accounts"})
    assert r.status_code == 200 and r.json()["rows"] == [[1]]


def test_load_demo_populates_store(empty_client):
    c, _ = empty_client
    r = c.post("/api/demo")
    assert r.status_code == 200
    assert any(s["name"] == "store" for s in r.json()["sources"])
    q = c.post("/api/query", json={"sql": "SELECT count(*) AS n FROM store.orders"})
    assert q.status_code == 200 and q.json()["rows"] == [[90]]


def test_load_demo_pristine_seeds_tour_parity(empty_client):
    # the launchpad demo must match the ephemeral tour: guides, evals, audit
    # chain, canaries, and the plain-english policy — not just the data.
    c, ws = empty_client
    assert c.post("/api/demo").status_code == 200
    assert (ws / "guides" / "analytics.md").exists()
    assert (ws / "evals" / "demo.yaml").exists()
    guides = c.get("/api/guides").json()["guides"]
    assert any("Revenue" in g["content"] for g in guides)
    entries = c.get("/api/audit").json()["entries"]
    assert len(entries) >= 2  # one allowed aggregate + one policy refusal
    tables = c.get("/api/tables").json()["tables"]
    canaries = [t for t in tables if t["table"] == "canaries"]
    assert canaries and any(a["masked"] for a in canaries[0]["access"].values())


def test_load_demo_on_nonpristine_workspace_stays_minimal(empty_client):
    # a workspace that already has real sources gets only the store source —
    # no policies, canaries, or seeded content forced into their charter.
    c, ws = empty_client
    con = sqlite3.connect(ws / "crm.db")
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.commit()
    con.close()
    src = {"name": "crm", "type": "sqlite", "path": "crm.db", "tables": ["accounts"]}
    assert c.post("/api/sources", json=src).status_code == 200
    assert c.post("/api/demo").status_code == 200
    assert "policies" not in (ws / "charter.yaml").read_text()
    assert not (ws / "guides" / "analytics.md").exists()
    assert c.get("/api/audit").json()["entries"] == []


def test_load_demo_is_idempotent(empty_client):
    c, _ = empty_client
    assert c.post("/api/demo").status_code == 200
    r2 = c.post("/api/demo")
    assert r2.status_code == 200
    assert len([s for s in r2.json()["sources"] if s["name"] == "store"]) == 1


def test_demo_tables_not_duplicated_as_uploads(empty_client):
    # the engine's flat compat-alias views (store__customers) must not appear in the
    # catalog listing — they duplicate store.customers and leak into the "uploads" group.
    c, _ = empty_client
    c.post("/api/demo")
    names = {t["table"] for t in c.get("/api/tables").json()["tables"]}
    assert "customers" in names and "orders" in names
    assert "store__customers" not in names and "store__orders" not in names


def test_delete_snapshot_removes_it(empty_client):
    c, ws = empty_client
    c.post("/api/demo")
    snap = c.post("/api/snapshot", json={"sql": "SELECT * FROM store.orders", "name": "snap"})
    assert snap.status_code == 200
    assert any(t["table"] == "snap" for t in c.get("/api/tables").json()["tables"])
    assert c.delete("/api/snapshot/snap").status_code == 200
    assert not any(t["table"] == "snap" for t in c.get("/api/tables").json()["tables"])
    assert not (ws / ".datacharter" / "snapshots" / "snap.sql").exists()


def test_delete_upload_removes_it(empty_client):
    c, ws = empty_client
    (ws / "u.csv").write_text("a,b\n1,2\n")
    with (ws / "u.csv").open("rb") as fh:
        assert c.post("/api/upload", files={"file": ("u.csv", fh, "text/csv")}).status_code == 200
    assert any(t["table"] == "u" for t in c.get("/api/tables").json()["tables"])
    assert c.delete("/api/uploads/u").status_code == 200
    assert not any(t["table"] == "u" for t in c.get("/api/tables").json()["tables"])


def test_delete_uploads_refuses_charter_source(empty_client):
    c, _ = empty_client
    c.post("/api/demo")  # `store` is a charter source
    assert c.delete("/api/uploads/store").status_code == 404


def test_load_demo_after_delete_reloads(empty_client):
    # deleting the source leaves demo/store.db on disk; reloading must not choke on it.
    c, _ = empty_client
    assert c.post("/api/demo").status_code == 200
    assert c.delete("/api/sources/store").status_code == 200
    r = c.post("/api/demo")
    assert r.status_code == 200
    assert any(s["name"] == "store" for s in r.json()["sources"])
    q = c.post("/api/query", json={"sql": "SELECT count(*) AS n FROM store.orders"})
    assert q.status_code == 200 and q.json()["rows"] == [[90]]
