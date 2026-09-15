"""MCP Streamable HTTP: POST /mcp reuses handle_message; stdio stays."""

import json

import pytest
from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.mcp.auth import AllowAll, AuthError, Principal
from datacharter.mcp.http import create_mcp_http_app
from datacharter.server import create_app


class _RejectAll:
    async def authenticate(self, request):  # noqa: ARG002
        raise AuthError(401, "nope")


@pytest.fixture
def client(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path, mcp_authenticator=AllowAll())
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def _rpc(method, id_=1, **params):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params:
        msg["params"] = params
    return msg


def test_initialize_over_http(client):
    resp = client.post("/mcp", json=_rpc("initialize", protocolVersion="2025-11-25"))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["result"]["protocolVersion"] == "2025-11-25"
    assert "tools" in body["result"]["capabilities"]
    assert body["result"]["serverInfo"]["name"] == "datacharter"


def test_tools_list_and_stateless_sequence(client):
    init = client.post("/mcp", json=_rpc("initialize", protocolVersion="2025-11-25"))
    assert init.status_code == 200
    listed = client.post("/mcp", json=_rpc("tools/list", id_=2))
    names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert {"list_sources", "list_tables", "describe_table", "query"} <= names
    called = client.post(
        "/mcp",
        json=_rpc("tools/call", id_=3, name="query", arguments={"sql": "SELECT 1 AS n"}),
    )
    assert called.status_code == 200
    result = called.json()["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["rows"] == [[1]]


def test_write_is_mcp_error_not_http_error(client):
    resp = client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            name="query",
            arguments={"sql": "DELETE FROM store.customers"},
        ),
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is True
    assert "read-only" in result["content"][0]["text"].lower()


def test_pii_is_masked(client):
    resp = client.post(
        "/mcp",
        json=_rpc(
            "tools/call",
            name="query",
            arguments={"sql": "SELECT email FROM store.customers LIMIT 1"},
        ),
    )
    text = resp.json()["result"]["content"][0]["text"]
    assert "ada@example.com" not in text
    payload = json.loads(text)
    assert payload["rows"][0][0] == "•••"


def test_get_mcp_is_405(client):
    resp = client.get("/mcp")
    assert resp.status_code == 405
    assert "POST" in resp.headers.get("allow", "")


def test_malformed_json_is_parse_error(client):
    resp = client.post("/mcp", content=b"{not json", headers={"content-type": "application/json"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == -32700
    assert body["id"] is None


def test_notification_is_202(client):
    resp = client.post(
        "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert resp.status_code == 202
    assert resp.content == b""


def test_foreign_origin_rejected(client):
    resp = client.post(
        "/mcp",
        json=_rpc("ping"),
        headers={"origin": "http://evil.example.com"},
    )
    assert resp.status_code == 403


def test_non_loopback_host_rejected_even_when_bind_is_open(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path, host="0.0.0.0", mcp_authenticator=AllowAll())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        resp = client.post(
            "/mcp",
            json=_rpc("ping"),
            headers={"host": "10.1.2.3:8321"},
        )
        assert resp.status_code == 403


def test_authenticator_seam_can_reject(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path, mcp_authenticator=_RejectAll())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        resp = client.post("/mcp", json=_rpc("ping"))
        assert resp.status_code == 401
        assert "nope" in resp.json()["error"]["message"]


def test_dedicated_mcp_http_app_pings(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_mcp_http_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/api/health").json()["transport"] == "mcp-http"
        assert c.post("/mcp", json=_rpc("ping")).status_code == 200


async def test_allow_all_returns_anonymous_principal():
    from starlette.requests import Request

    from datacharter.mcp.auth import AllowAll

    req = Request({"type": "http", "headers": []})
    principal = await AllowAll().authenticate(req)
    assert isinstance(principal, Principal)
    assert principal.subject is None
