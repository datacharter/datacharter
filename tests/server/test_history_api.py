"""Explicit runs (record:true) land in history; preview does not; GET /api/history."""

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


def test_recorded_run_appears_in_history(client):
    client.post("/api/query", json={"sql": "SELECT 42 AS answer", "record": True})
    entries = client.get("/api/history").json()["entries"]
    assert entries and entries[0]["sql"] == "SELECT 42 AS answer"
    assert entries[0]["row_count"] == 1


def test_preview_not_recorded(client):
    client.post("/api/query", json={"sql": "SELECT 7"})  # no record flag
    assert client.get("/api/history").json()["entries"] == []
