"""POST /api/agent-access persists overrides; /api/tables exposes effective access;
the agent surface (/api/tool) reflects it while the human /api/query stays unmasked."""

import json

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
def client(tmp_path):
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    cli_main(["init", str(tmp_path), "--demo"])
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as c:
        yield c
    keyring.set_keyring(prev)


def _access(c, relation_table):
    for t in c.get("/api/tables").json()["tables"]:
        if t["table"] == relation_table:
            return t["access"]
    return {}


def _tool_query(c, sql):
    r = c.post("/api/tool", json={"name": "query", "arguments": json.dumps({"sql": sql})})
    return json.loads(r.json()["result"])


def test_tables_reports_effective_access(client):
    acc = _access(client, "customers")
    assert acc["email"]["masked"] is True and acc["email"]["pii"] is True
    assert acc["tier"]["masked"] is False


def test_unmask_pii_then_agent_sees_real(client):
    # agent sees masked by default
    assert _tool_query(client, "SELECT email FROM store.customers LIMIT 1")["rows"][0][0] == "•••"
    # unmask email for the agent
    body = {"source": "store", "table": "customers", "column": "email", "value": True}
    r = client.post("/api/agent-access", json=body)
    assert r.status_code == 200
    assert _access(client, "customers")["email"]["masked"] is False
    out = _tool_query(client, "SELECT email FROM store.customers LIMIT 1")
    assert "@" in out["rows"][0][0]  # agent now sees real


def test_human_query_unaffected_by_mask(client):
    off = {"source": "store", "table": "customers", "column": "email", "value": False}
    client.post("/api/agent-access", json=off)
    r = client.post("/api/query", json={"sql": "SELECT email FROM store.customers LIMIT 1"})
    assert "@" in r.json()["rows"][0][0]  # human editor is never masked


def test_unknown_source_404(client):
    r = client.post("/api/agent-access", json={"source": "ghost", "column": "x", "value": True})
    assert r.status_code == 404
