"""`datacharter connect` — the MCP-server config for popular clients.

Copy-pasting JSON into the right file is the #1 onboarding drop-off. This prints
the exact config block, the file it goes in, and a one-click install **deeplink**
where the client supports one — for Claude Desktop, Claude Code, Cursor, VS Code,
Cline, Windsurf, and LM Studio. With `--serve-url` it emits HTTP config for a
running `datacharter serve` instead of the local stdio server.
"""

from __future__ import annotations

import base64
import json
import platform
import urllib.parse
from pathlib import Path

CLIENTS = ["claude-desktop", "claude-code", "cursor", "vscode", "cline", "windsurf", "lmstudio"]


def server_entry(workspace: str | None, serve_url: str | None) -> dict:
    """The MCP server config the client runs: HTTP when `serve_url` is set, else the
    local governed stdio server (`datacharter mcp <workspace>`) via an absolute
    binary path (bare `uvx`/`datacharter` fails under a GUI client's minimal PATH)."""
    if serve_url:
        return {"type": "http", "url": serve_url}
    from datacharter.agent.claude_code import _dc_bin

    return {"command": _dc_bin(), "args": ["mcp", str(Path(workspace or ".").resolve())]}


def _claude_desktop_path() -> str:
    system = platform.system()
    if system == "Darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    if system == "Windows":
        return "%APPDATA%\\Claude\\claude_desktop_config.json"
    return "~/.config/Claude/claude_desktop_config.json"


def _b64(entry: dict) -> str:
    return base64.b64encode(json.dumps(entry).encode()).decode()


def deeplink(client: str, name: str, entry: dict) -> str | None:
    """A one-click install URL for clients that support one, else None."""
    if client == "cursor":
        return f"cursor://anysphere.cursor-deeplink/mcp/install?name={name}&config={_b64(entry)}"
    if client == "vscode":
        payload = urllib.parse.quote(json.dumps({"name": name, **entry}))
        return f"vscode:mcp/install?{payload}"
    if client == "lmstudio":
        return f"lmstudio://add_mcp?name={name}&config={_b64(entry)}"
    return None


# client -> (label, config file, root key). VS Code uses `servers`, not `mcpServers`.
_FILES = {
    "claude-desktop": ("Claude Desktop", _claude_desktop_path, "mcpServers"),
    "cursor": ("Cursor", lambda: "~/.cursor/mcp.json", "mcpServers"),
    "vscode": ("VS Code", lambda: ".vscode/mcp.json", "servers"),
    "cline": ("Cline", lambda: "cline_mcp_settings.json (VS Code globalStorage)", "mcpServers"),
    "windsurf": ("Windsurf", lambda: "~/.codeium/windsurf/mcp_config.json", "mcpServers"),
    "lmstudio": ("LM Studio", lambda: "mcp.json", "mcpServers"),
}


def render(client: str, name: str, entry: dict) -> list[str]:
    """The instructions block for one client."""
    if client == "claude-code":
        if entry.get("type") == "http":
            cmd = f"claude mcp add --transport http {name} {entry['url']}"
        else:
            args = " ".join(entry["args"])
            cmd = f"claude mcp add {name} -- {entry['command']} {args}"
        return ["── Claude Code ──", "  run:", f"    {cmd}"]

    label, path_fn, root = _FILES[client]
    block = json.dumps({root: {name: entry}}, indent=2)
    out = [f"── {label} ──", f"  file: {path_fn()}",
           "  add (merge with any existing servers):",
           *("    " + line for line in block.splitlines())]
    link = deeplink(client, name, entry)
    if link:
        out += ["  or one-click:", f"    {link}"]
    return out


def run(directory: str | None, client: str | None, serve_url: str | None) -> int:
    entry = server_entry(directory, serve_url)
    name = "datacharter"
    targets = [client] if client and client != "all" else CLIENTS
    print()
    for c in targets:
        for line in render(c, name, entry):
            print(line)
        print()
    hint = "a running `datacharter serve`" if serve_url else "the local governed stdio server"
    print(f"  Points each client at {hint}. Restart the client after adding it.")
    return 0
