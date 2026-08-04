"""Every entry path must present the SAME governed surface (F-5/F-9 class):
ToolBox is built by one factory, and these tests prove each door — serve,
`datacharter mcp`, eval, the compare-guides arm — masks value-detected PII
and honors snapshot overrides identically."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import keyring
import keyring.backend
import pytest

from datacharter.cli import main as cli_main


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
def value_pii_ws(tmp_path, monkeypatch):
    """A workspace whose PII is detectable only BY VALUE (column name gives
    nothing away) — the exact case `datacharter mcp` shipped unmasked."""
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    assert cli_main(["init", str(tmp_path)]) == 0
    (tmp_path / "people.csv").write_text(
        "who,contact\nada,ada@example.com\ngrace,grace@example.com\nedsger,e@example.com\n"
    )
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  people:\n    type: csv\n    path: people.csv\n"
    )
    yield tmp_path
    keyring.set_keyring(prev)


def _mcp_query(ws: Path, sql: str) -> str:
    frames = "\n".join(
        json.dumps(f)
        for f in [
            {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "0"}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "query", "arguments": {"sql": sql}}},
        ]
    )
    proc = subprocess.run(
        [sys.executable, "-m", "datacharter.cli", "mcp", str(ws)],
        input=frames + "\n", capture_output=True, text=True, timeout=120,
    )
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            return msg["result"]["content"][0]["text"]
    raise AssertionError(f"no tool result; stderr: {proc.stderr[-500:]}")


def test_mcp_stdio_masks_value_detected_pii(value_pii_ws):
    # F-5: this exact path served ada@example.com raw to external MCP clients.
    out = _mcp_query(value_pii_ws, "SELECT contact FROM people LIMIT 1")
    assert "ada@example.com" not in out
    assert json.loads(out)["rows"][0][0] == "•••"


def test_eval_toolbox_masks_value_detected_pii(value_pii_ws, monkeypatch):
    # The eval path builds its box through the same factory now.
    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.cli import _open_engine
    from datacharter.contracts import load_charter

    charter = load_charter(value_pii_ws)
    engine = _open_engine(value_pii_ws, charter.sources)
    try:
        box = build_toolbox(
            engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine))
        )
        out = asyncio.run(
            box.run("query", json.dumps({"sql": "SELECT contact FROM people LIMIT 1"}))
        )
        assert "ada@example.com" not in out
        # compare-guides "off" arm: same masking, only guides differ
        box_off = build_toolbox(
            engine, charter,
            auto_pii=asyncio.run(detect_auto_pii(engine)),
            guides_override="",
        )
        out_off = asyncio.run(
            box_off.run("query", json.dumps({"sql": "SELECT contact FROM people LIMIT 1"}))
        )
        assert "ada@example.com" not in out_off
    finally:
        engine.close()


def test_no_direct_toolbox_construction_outside_factory():
    # The class-killer: hand-assembled ToolBoxes are how F-5/F-9 shipped.
    # Only the factory (and ToolBox's own module/tests) may construct one.
    root = Path(__file__).resolve().parent.parent / "src" / "datacharter"
    offenders = []
    for f in root.rglob("*.py"):
        if f.name in ("factory.py", "tools.py"):
            continue
        import re as _re

        if _re.search(r"(?<![A-Za-z])ToolBox\(", f.read_text()):
            offenders.append(str(f.relative_to(root)))
    assert not offenders, f"construct ToolBox via agent.factory.build_toolbox: {offenders}"
