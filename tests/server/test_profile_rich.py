"""/api/profile returns SUMMARIZE rows plus per-column top values."""

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


def test_profile_returns_top_values(client):
    sql = "SELECT 'a' AS g FROM range(2) UNION ALL SELECT 'b' FROM range(1)"
    body = client.post("/api/profile", json={"sql": sql}).json()
    assert body["columns"]  # SUMMARIZE rows still present
    assert body["top_values"]["g"][0] == ["a", 2]
    assert body["top_values"]["g"][1] == ["b", 1]
