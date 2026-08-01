"""Every ToolBox.run() call lands in the flight recorder — success and error alike."""

import asyncio
import json

from datacharter.agent.tools import ToolBox
from datacharter.audit.evidence import read_entries, verify_chain
from datacharter.audit.recorder import FlightRecorder
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def _box(tmp_path, recorder):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    return eng, ToolBox(eng, charter.sources, recorder=recorder)


def test_query_recorded_with_metadata(tmp_path):
    rec = FlightRecorder(tmp_path)
    rec.start_session("chat", model="test-model")
    eng, box = _box(tmp_path, rec)
    try:
        asyncio.run(box.run("query", json.dumps({"sql": "SELECT email FROM store.customers"})))
    finally:
        eng.close()
    access = [e for e in read_entries(tmp_path) if e["type"] == "access"]
    assert len(access) == 1
    e = access[0]
    assert e["tool"] == "query"
    assert e["sql"].startswith("SELECT email")
    assert e["masked_columns"] == ["email"]
    assert e["row_count"] > 0
    assert e["result_sha256"]
    ok, _, _ = verify_chain(tmp_path)
    assert ok


def test_error_calls_recorded(tmp_path):
    rec = FlightRecorder(tmp_path)
    rec.start_session("chat")
    eng, box = _box(tmp_path, rec)
    try:
        asyncio.run(box.run("query", json.dumps({"sql": "DELETE FROM store.customers"})))
        asyncio.run(box.run("nope", "{}"))
    finally:
        eng.close()
    access = [e for e in read_entries(tmp_path) if e["type"] == "access"]
    assert len(access) == 2
    assert all(a["error"].startswith("Error:") for a in access)


def test_no_recorder_is_fine(tmp_path):
    eng, box = _box(tmp_path, None)
    try:
        out = asyncio.run(box.run("query", json.dumps({"sql": "SELECT 1 AS n"})))
    finally:
        eng.close()
    assert json.loads(out)["rows"] == [[1]]


def test_broken_recorder_never_breaks_the_query(tmp_path, monkeypatch):
    rec = FlightRecorder(tmp_path)
    rec.start_session("chat")
    monkeypatch.setattr(
        rec, "_tail", lambda: (_ for _ in ()).throw(OSError("disk gone"))
    )
    eng, box = _box(tmp_path, rec)
    try:
        out = asyncio.run(box.run("query", json.dumps({"sql": "SELECT 1 AS n"})))
    finally:
        eng.close()
    assert json.loads(out)["rows"] == [[1]]
