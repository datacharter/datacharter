import base64
import json
import urllib.parse

from datacharter.agent import connect


def test_server_entry_stdio(tmp_path):
    entry = connect.server_entry(str(tmp_path), None)
    assert entry["args"] == ["mcp", str(tmp_path.resolve())]
    assert entry["command"].endswith("datacharter") or "datacharter" in entry["command"]


def test_server_entry_http():
    assert connect.server_entry(".", "http://127.0.0.1:8765") == {
        "type": "http", "url": "http://127.0.0.1:8765"
    }


def test_vscode_uses_servers_key_others_use_mcpservers():
    entry = {"command": "datacharter", "args": ["mcp", "/ws"]}
    cursor = "\n".join(connect.render("cursor", "datacharter", entry))
    vscode = "\n".join(connect.render("vscode", "datacharter", entry))
    assert '"mcpServers"' in cursor
    assert '"servers"' in vscode and '"mcpServers"' not in vscode  # the #1 generator bug


def test_claude_code_is_a_command_not_a_file():
    entry = {"command": "dc", "args": ["mcp", "/ws"]}
    stdio = "\n".join(connect.render("claude-code", "datacharter", entry))
    assert "claude mcp add datacharter -- dc mcp /ws" in stdio
    http = "\n".join(connect.render("claude-code", "datacharter", {"type": "http", "url": "http://h"}))
    assert "claude mcp add --transport http datacharter http://h" in http


def test_deeplinks():
    entry = {"command": "dc", "args": ["mcp", "/ws"]}
    cursor = connect.deeplink("cursor", "datacharter", entry)
    assert cursor.startswith("cursor://anysphere.cursor-deeplink/mcp/install?name=datacharter&config=")
    assert json.loads(base64.b64decode(cursor.split("config=")[1])) == entry  # base64
    vscode = connect.deeplink("vscode", "datacharter", entry)
    payload = json.loads(urllib.parse.unquote(vscode.split("?", 1)[1]))  # url-encoded
    assert payload == {"name": "datacharter", **entry}
    assert connect.deeplink("lmstudio", "datacharter", entry).startswith("lmstudio://add_mcp?")
    assert connect.deeplink("claude-desktop", "datacharter", entry) is None  # no deeplink


def test_run_all_clients_lists_each(capsys):
    assert connect.run(".", "all", None) == 0
    out = capsys.readouterr().out
    labels = ("Claude Desktop", "Claude Code", "Cursor", "VS Code",
              "Cline", "Windsurf", "LM Studio")
    for label in labels:
        assert label in out


def test_run_single_client_shows_only_it(tmp_path, capsys):
    assert connect.run(str(tmp_path), "cursor", None) == 0
    out = capsys.readouterr().out
    assert "Cursor" in out and "cursor://" in out
    assert "Claude Desktop" not in out


def test_run_serve_url_emits_http(capsys):
    assert connect.run(None, "claude-code", "http://127.0.0.1:8765") == 0
    out = capsys.readouterr().out
    assert "claude mcp add --transport http datacharter http://127.0.0.1:8765" in out
    assert "running `datacharter serve`" in out
