import json
import zipfile

from datacharter.audit.evidence import export_pack, read_entries, verify_chain
from datacharter.audit.recorder import FLIGHT_DIR, FlightRecorder


def _seed(ws, n=4):
    (ws / "charter.yaml").write_text("version: 1\nsources: {}\n")
    r = FlightRecorder(ws)
    r.start_session("mcp", client={"name": "cursor", "version": "1"})
    rendered = json.dumps({"columns": ["n"], "rows": [[1]], "row_count": 1, "truncated": False})
    for i in range(n):
        r.record_access("query", json.dumps({"sql": f"SELECT {i}"}), rendered)
    return ws


def _segment(ws):
    return sorted((ws / FLIGHT_DIR).glob("[0-9]*.jsonl"))[0]


def test_read_entries_ordered(tmp_path):
    _seed(tmp_path)
    e = read_entries(tmp_path)
    assert [x["seq"] for x in e] == [1, 2, 3, 4, 5]
    assert e[0]["type"] == "session"


def test_verify_ok(tmp_path):
    _seed(tmp_path)
    ok, n, detail = verify_chain(tmp_path)
    assert ok is True and n == 5
    assert "verified" in detail


def test_verify_detects_edited_entry(tmp_path):
    _seed(tmp_path)
    seg = _segment(tmp_path)
    lines = seg.read_text().splitlines()
    doctored = json.loads(lines[2])
    doctored["sql"] = "SELECT * FROM secrets"  # rewrite history
    lines[2] = json.dumps(doctored)
    seg.write_text("\n".join(lines) + "\n")
    ok, _, detail = verify_chain(tmp_path)
    assert ok is False
    assert "seq 3" in detail


def test_verify_detects_deleted_entry(tmp_path):
    _seed(tmp_path)
    seg = _segment(tmp_path)
    lines = seg.read_text().splitlines()
    del lines[2]
    seg.write_text("\n".join(lines) + "\n")
    ok, _, detail = verify_chain(tmp_path)
    assert ok is False


def test_time_window_filter(tmp_path):
    _seed(tmp_path)
    all_e = read_entries(tmp_path)
    mid_ts = all_e[2]["ts"]
    later = read_entries(tmp_path, since=mid_ts)
    assert later[0]["seq"] == 3
    earlier = read_entries(tmp_path, until=mid_ts)
    assert earlier[-1]["seq"] == 3


def test_export_pack_contents(tmp_path):
    _seed(tmp_path)
    out = export_pack(tmp_path, tmp_path / "evidence.zip")
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert {"entries.jsonl", "verification.txt", "charter.yaml", "summary.md"} <= names
        assert b"verified" in z.read("verification.txt")
        summary = z.read("summary.md").decode()
        assert "query" in summary and "1" in summary


def test_verify_empty_workspace(tmp_path):
    ok, n, _ = verify_chain(tmp_path)
    assert ok is True and n == 0
