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
def client(tmp_path):
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    con = sqlite3.connect(tmp_path / "crm.db")
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.commit()
    con.close()
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c
    keyring.set_keyring(prev)


def test_add_edit_delete_sqlite(client):
    body = {"name": "crm", "type": "sqlite", "path": "crm.db", "tables": ["accounts"]}
    assert client.post("/api/sources", json=body).status_code == 200
    got = client.get("/api/sources").json()["sources"]
    assert any(s["name"] == "crm" for s in got)

    body["pii"] = {"accounts": ["org"]}
    assert client.put("/api/sources/crm", json=body).status_code == 200

    assert client.delete("/api/sources/crm").status_code == 200
    got = client.get("/api/sources").json()["sources"]
    assert all(s["name"] != "crm" for s in got)


def test_edit_missing_source_404(client):
    body = {"name": "ghost", "type": "sqlite", "path": "crm.db"}
    assert client.put("/api/sources/ghost", json=body).status_code == 404


def test_test_connection_reports_failure(client):
    bad = {"name": "nope", "type": "postgres", "connection": {"host": "x", "user": "u"}}
    assert client.post("/api/sources/test", json=bad).status_code == 400


def test_get_sources_has_connection_and_credential_flag(client):
    got = client.get("/api/sources").json()["sources"]
    for s in got:
        assert "connection" in s and "has_credential" in s
