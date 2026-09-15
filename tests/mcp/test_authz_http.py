"""MCP HTTP applies charter grants to the authenticated principal."""

import json

from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.mcp.auth import Principal
from datacharter.server import create_app

CHARTER = """\
version: 1
sources:
  store:
    type: sqlite
    path: demo/store.db
    tables: [customers, orders]
principals:
  analyst: alice@corp
grants:
  analyst:
    - store.orders
"""


class _FixedAuth:
    def __init__(self, subject: str):
        self._subject = subject

    async def authenticate(self, request):  # noqa: ARG002
        return Principal(subject=self._subject)


def _client(tmp_path, subject="alice@corp"):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    (tmp_path / "charter.yaml").write_text(CHARTER)
    app = create_app(tmp_path, mcp_authenticator=_FixedAuth(subject))
    return TestClient(app, base_url="http://127.0.0.1")


def _call(name, **arguments):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def test_list_tables_pruned_to_grants(tmp_path):
    with _client(tmp_path) as c:
        body = c.post("/mcp", json=_call("list_tables")).json()
        rels = {r["relation"] for r in json.loads(body["result"]["content"][0]["text"])}
        assert "store.orders" in rels
        assert "store.customers" not in rels


def test_query_customers_is_error_orders_ok(tmp_path):
    with _client(tmp_path) as c:
        denied = c.post(
            "/mcp",
            json=_call("query", sql="SELECT 1 FROM store.customers"),
        ).json()
        assert denied["result"]["isError"] is True
        ok = c.post(
            "/mcp",
            json=_call("query", sql="SELECT count(*) AS n FROM store.orders"),
        ).json()
        assert ok["result"]["isError"] is False


def test_unknown_subject_denied(tmp_path):
    with _client(tmp_path, subject="intruder") as c:
        body = c.post("/mcp", json=_call("list_tables")).json()
        rels = json.loads(body["result"]["content"][0]["text"])
        assert rels == []


def test_denied_query_records_principal_on_chain(tmp_path):
    from datacharter.audit.recorder import FLIGHT_DIR

    with _client(tmp_path) as c:
        c.post("/mcp", json=_call("query", sql="SELECT 1 FROM store.customers"))
    accesses = []
    for seg in (tmp_path / FLIGHT_DIR).glob("[0-9]*.jsonl"):
        for line in seg.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                if e.get("type") == "access":
                    accesses.append(e)
    denied = [e for e in accesses if "not authorized" in (e.get("error") or "")]
    assert denied
    assert denied[0]["principal"] == "alice@corp"
