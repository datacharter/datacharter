"""POST /api/explain returns a plan and a best-effort row estimate (None when absent)."""

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


def test_explain_returns_estimate(client):
    body = client.post(
        "/api/explain", json={"sql": "SELECT * FROM store.orders WHERE total > 10"}
    ).json()
    assert isinstance(body["plan"], str) and body["plan"]
    assert isinstance(body["estimated_rows"], int)


def test_explain_aggregate_has_no_estimate(client):
    body = client.post("/api/explain", json={"sql": "SELECT count(*) FROM store.orders"}).json()
    assert body["estimated_rows"] is None


def test_explain_rejects_non_query(client):
    resp = client.post("/api/explain", json={"sql": "DROP TABLE store.orders"})
    assert resp.status_code == 400
