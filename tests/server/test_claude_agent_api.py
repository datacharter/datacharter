"""Server wiring for the Claude Code agent backend — no real `claude` (mocked)."""

import keyring
import keyring.backend
import pytest
from fastapi.testclient import TestClient

from datacharter.agent import claude_code as cc
from datacharter.cli import main as cli_main
from datacharter.server import agent_backend, create_app


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
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c, tmp_path
    keyring.set_keyring(prev)


def test_available_reports_claude(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(cc, "claude_available", lambda: True)
    body = c.get("/api/agent/available").json()
    assert body["claude_code_available"] is True and body["backend"] == "llm"


def test_connect_success_sets_backend(client, monkeypatch):
    c, ws = client

    async def _ok(serve_url, dc_bin=None, initial_deny=None):
        return ["Bash"]  # effective deny-list (surface verified clean)

    monkeypatch.setattr(cc, "claude_available", lambda: True)
    monkeypatch.setattr(cc, "assert_tool_surface", _ok)
    r = c.post("/api/agent/claude-code/connect")
    assert r.status_code == 200 and r.json()["backend"] == "claude-code"
    assert agent_backend.get_backend(ws) == "claude-code"


def test_connect_refuses_on_governance(client, monkeypatch):
    c, ws = client

    async def _boom(serve_url, dc_bin=None, initial_deny=None):
        raise cc.ClaudeGovernanceError("exposes non-governed tools: Bash")

    monkeypatch.setattr(cc, "claude_available", lambda: True)
    monkeypatch.setattr(cc, "assert_tool_surface", _boom)
    r = c.post("/api/agent/claude-code/connect")
    assert r.status_code == 400 and "Bash" in r.json()["error"]["message"]
    assert agent_backend.get_backend(ws) == "llm"  # unchanged — fail closed


def test_connect_needs_claude_installed(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(cc, "claude_available", lambda: False)
    assert c.post("/api/agent/claude-code/connect").status_code == 400


def test_switch_backend_back_to_llm(client):
    c, ws = client
    agent_backend.set_backend(ws, "claude-code")
    r = c.post("/api/agent/backend", json={"backend": "llm"})
    assert r.status_code == 200 and agent_backend.get_backend(ws) == "llm"
    assert c.post("/api/agent/backend", json={"backend": "bogus"}).status_code == 400


def _connect_cc(c, monkeypatch):
    async def _ok(serve_url, dc_bin=None, initial_deny=None):
        return ["Bash"]

    monkeypatch.setattr(cc, "claude_available", lambda: True)
    monkeypatch.setattr(cc, "assert_tool_surface", _ok)
    assert c.post("/api/agent/claude-code/connect").status_code == 200


def test_claude_code_reuses_session_across_turns(client, monkeypatch):
    c, _ = client
    _connect_cc(c, monkeypatch)

    received: list[str | None] = []

    async def fake_run_turn(
        question, serve_url, session_id=None, dc_bin=None, deny=None, context=None
    ):
        received.append(session_id)
        yield {"kind": "session", "session_id": "sess-123", "tools": []}
        yield {"kind": "text", "text": "ok"}
        yield {"kind": "result", "session_id": "sess-123", "text": "ok", "is_error": False}

    monkeypatch.setattr(cc, "run_turn", fake_run_turn)
    assert c.post("/api/agent/ask", json={"question": "how many customers?"}).status_code == 200
    assert c.post("/api/agent/ask", json={"question": "what are their emails?"}).status_code == 200
    # Turn 2 must resume turn 1's session — otherwise every turn is a cold start.
    assert received == [None, "sess-123"]


def test_unmasking_keeps_claude_session(client, monkeypatch):
    c, _ = client
    _connect_cc(c, monkeypatch)
    c.app.state.cc_session = {"id": "keep-me"}
    r = c.post(
        "/api/agent-access",
        json={"source": "store", "table": "customers", "column": "email", "value": True},
    )
    assert r.status_code == 200
    # Loosening access must NOT wipe the conversation.
    assert c.app.state.cc_session == {"id": "keep-me"}


def test_masking_resets_claude_session(client, monkeypatch):
    c, _ = client
    _connect_cc(c, monkeypatch)
    c.app.state.cc_session = {"id": "drop-me"}
    r = c.post(
        "/api/agent-access",
        json={"source": "store", "table": "customers", "column": "email", "value": False},
    )
    assert r.status_code == 200
    # Tightening access drops the session so a now-masked value can't be echoed.
    assert c.app.state.cc_session == {}
