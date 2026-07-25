"""The cold-start journey a real adopter takes: `datacharter init` (empty, NO --demo)
-> serve -> run a query -> add your own source -> query it. This path was never
exercised (every other server test inits with --demo), which let two demo-only
assumptions ship — the loader rejecting empty `sources`, and the onboarding running a
hardcoded `store.orders` query. This guards the whole class at the integration level.
"""

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


def test_load_demo_is_idempotent(empty_client):
    c, _ = empty_client
    assert c.post("/api/demo").status_code == 200
    r2 = c.post("/api/demo")
    assert r2.status_code == 200
    assert len([s for s in r2.json()["sources"] if s["name"] == "store"]) == 1
