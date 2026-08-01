import hashlib
import json

from datacharter.audit import recorder as rec_mod
from datacharter.audit.recorder import FLIGHT_DIR, GENESIS, FlightRecorder, canonical_hash


def _entries(ws):
    out = []
    for seg in sorted((ws / FLIGHT_DIR).glob("[0-9]*.jsonl")):
        for line in seg.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def _rendered(row_count=2, masked=None, relations=None):
    p = {"columns": ["a"], "rows": [[1], [2]], "row_count": row_count, "truncated": False}
    if masked:
        p["masked_columns"] = masked
    if relations:
        p["provenance"] = {"relations": relations}
    return json.dumps(p)


def test_first_entry_uses_genesis_and_chains(tmp_path):
    r = FlightRecorder(tmp_path)
    r.start_session("mcp", client={"name": "cursor", "version": "1.4"})
    r.record_access("query", json.dumps({"sql": "SELECT 1"}), _rendered())
    e = _entries(tmp_path)
    assert len(e) == 2
    assert e[0]["prev"] == GENESIS and e[0]["seq"] == 1
    assert e[1]["prev"] == e[0]["hash"] and e[1]["seq"] == 2


def test_hash_is_canonical_sha256_of_entry_minus_hash(tmp_path):
    r = FlightRecorder(tmp_path)
    r.start_session("chat", model="gpt-4o-mini", question="how many orders?")
    e = _entries(tmp_path)[0]
    body = {k: v for k, v in e.items() if k != "hash"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    assert e["hash"] == hashlib.sha256(blob.encode()).hexdigest()
    assert canonical_hash(e) == e["hash"]


def test_session_entry_dual_attribution(tmp_path):
    r = FlightRecorder(tmp_path)
    r.start_session("mcp", client={"name": "claude-desktop", "version": "2"})
    e = _entries(tmp_path)[0]
    assert e["type"] == "session"
    assert e["surface"] == "mcp"
    assert e["client"]["name"] == "claude-desktop"
    assert isinstance(e["user"], str) and e["user"]


def test_access_entry_metadata_and_result_hash(tmp_path):
    r = FlightRecorder(tmp_path)
    r.start_session("chat")
    rendered = _rendered(masked=["email"], relations=["crm.customers"])
    r.record_access("query", json.dumps({"sql": "SELECT email FROM crm.customers"}), rendered)
    e = _entries(tmp_path)[1]
    assert e["sql"].startswith("SELECT email")
    assert e["row_count"] == 2
    assert e["masked_columns"] == ["email"]
    assert e["relations"] == ["crm.customers"]
    assert e["result_sha256"] == hashlib.sha256(rendered.encode()).hexdigest()
    # raw rows never stored
    assert "rows" not in e


def test_error_result_recorded_without_hash(tmp_path):
    r = FlightRecorder(tmp_path)
    r.start_session("chat")
    r.record_access("query", json.dumps({"sql": "DELETE FROM x"}), "Error: writes are blocked")
    e = _entries(tmp_path)[1]
    assert e["error"].startswith("Error:")
    assert e["result_sha256"] is None


def test_disabled_recorder_writes_nothing(tmp_path):
    r = FlightRecorder(tmp_path, enabled=False)
    assert r.start_session("chat") == ""
    r.record_access("query", "{}", _rendered())
    assert not (tmp_path / FLIGHT_DIR).exists()


def test_segment_rotation_preserves_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(rec_mod, "_SEGMENT_MAX_BYTES", 200)
    r = FlightRecorder(tmp_path)
    r.start_session("chat")
    for i in range(5):
        r.record_access("query", json.dumps({"sql": f"SELECT {i}"}), _rendered())
    segs = sorted((tmp_path / FLIGHT_DIR).glob("[0-9]*.jsonl"))
    assert len(segs) >= 2
    e = _entries(tmp_path)
    assert [x["seq"] for x in e] == list(range(1, len(e) + 1))
    for prev_e, cur in zip(e, e[1:], strict=False):
        assert cur["prev"] == prev_e["hash"]
