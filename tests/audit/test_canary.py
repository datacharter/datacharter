"""Canary tripwires: planting, masking, detection, block/log, chain alarms."""

import asyncio
import json

import pytest

from datacharter.agent.tools import MASKED, ToolBox
from datacharter.audit.canary import CANARY_FILE, CanaryGuard, ensure_canaries
from datacharter.audit.evidence import read_entries, verify_chain
from datacharter.audit.recorder import FlightRecorder
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.contracts.loader import CharterError
from datacharter.engine.session import Engine


@pytest.fixture
def demo(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield tmp_path, eng, charter
    finally:
        eng.close()


# --- loader modes -----------------------------------------------------------

def test_loader_canary_modes(tmp_path):
    cli_main(["init", str(tmp_path)])
    base = (tmp_path / "charter.yaml").read_text()

    assert load_charter(tmp_path).canary_mode is None
    (tmp_path / "charter.yaml").write_text(base + "\ncanary: on\n")
    assert load_charter(tmp_path).canary_mode == "block"
    (tmp_path / "charter.yaml").write_text(base + "\ncanary: { mode: log }\n")
    assert load_charter(tmp_path).canary_mode == "log"
    (tmp_path / "charter.yaml").write_text(base + "\ncanary: off\n")
    assert load_charter(tmp_path).canary_mode is None
    (tmp_path / "charter.yaml").write_text(base + "\ncanary: maybe\n")
    with pytest.raises(CharterError, match="canary"):
        load_charter(tmp_path)


# --- planting ---------------------------------------------------------------

def test_planting_creates_table_and_stable_tokens(demo):
    ws, eng, _ = demo
    g1 = ensure_canaries(ws, eng, "block")
    assert g1 is not None and len(g1.tokens) == 3
    assert (ws / CANARY_FILE).exists()
    g2 = ensure_canaries(ws, eng, "block")
    assert g2.tokens == g1.tokens  # stable across sessions
    rows = eng.query_sync("SELECT email, phone, ssn FROM local.canaries").rows
    assert len(rows) == 3
    assert all(g1.tokens[i] in rows[i][0] for i in range(3))


def test_disabled_returns_none(demo):
    ws, eng, _ = demo
    assert ensure_canaries(ws, eng, None) is None


# --- no false positives: masking hides canaries -----------------------------

def test_masked_canary_query_raises_no_alarm(demo):
    ws, eng, charter = demo
    guard = ensure_canaries(ws, eng, "block")
    rec = FlightRecorder(ws)
    rec.start_session("chat")
    box = ToolBox(eng, charter.sources, recorder=rec, canary=guard)
    out = asyncio.run(
        box.run("query", json.dumps({"sql": "SELECT email FROM local.canaries"}))
    )
    payload = json.loads(out)
    assert all(row[0] == MASKED for row in payload["rows"])  # masked as designed
    assert not [e for e in read_entries(ws) if e["type"] == "alarm"]


# --- detection: block vs log ------------------------------------------------

class _LeakyBox(ToolBox):
    """Simulates a masking failure by leaking a canary token in the result."""

    def __init__(self, leak, **kw):
        super().__init__(**kw)
        self._leak = leak

    async def _dispatch(self, name, arguments):
        return json.dumps({"columns": ["email"], "rows": [[self._leak]],
                           "row_count": 1, "truncated": False})


def _leaky(demo_tuple, mode):
    ws, eng, charter = demo_tuple
    guard = ensure_canaries(ws, eng, mode)
    rec = FlightRecorder(ws)
    rec.start_session("chat")
    leak = guard.tokens[0] + "@tripwire.invalid"
    box = _LeakyBox(leak, engine=eng, sources=charter.sources, recorder=rec, canary=guard)
    return ws, box, leak


def test_block_mode_withholds_and_alarms(demo):
    ws, box, _ = _leaky(demo, "block")
    out = asyncio.run(box.run("query", json.dumps({"sql": "SELECT email FROM x"})))
    assert out.startswith("Error: canary tripwire")
    entries = read_entries(ws)
    alarms = [e for e in entries if e["type"] == "alarm"]
    assert len(alarms) == 1 and alarms[0]["kind"] == "canary"
    access = [e for e in entries if e["type"] == "access"]
    assert access[-1]["error"].startswith("Error: canary tripwire")
    ok, _, _ = verify_chain(ws)
    assert ok  # alarms are chain entries too


def test_log_mode_passes_through_and_alarms(demo):
    ws, box, leak = _leaky(demo, "log")
    out = asyncio.run(box.run("query", json.dumps({"sql": "SELECT email FROM x"})))
    assert leak in out  # passed through
    alarms = [e for e in read_entries(ws) if e["type"] == "alarm"]
    assert len(alarms) == 1


# --- guard scan unit --------------------------------------------------------

def test_guard_scan():
    g = CanaryGuard(tokens=["canary-abc123"], mode="block")
    assert g.scan("… canary-abc123@tripwire.invalid …") == "canary-abc123"
    assert g.scan("nothing here") is None
