import json

from datacharter.audit.recorder import FLIGHT_DIR, FlightRecorder
from datacharter.cli import main as cli_main


def _seed(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    r = FlightRecorder(tmp_path)
    r.start_session("mcp", client={"name": "cursor", "version": "1"})
    rendered = json.dumps({"columns": ["n"], "rows": [[1]], "row_count": 1, "truncated": False})
    r.record_access("query", json.dumps({"sql": "SELECT 1"}), rendered)


def test_audit_show_lists_sessions(tmp_path, capsys):
    _seed(tmp_path)
    assert cli_main(["audit", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "cursor" in out and "[mcp]" in out and "verified" in out


def test_audit_verify_ok_and_tampered(tmp_path, capsys):
    _seed(tmp_path)
    assert cli_main(["audit", str(tmp_path), "verify"]) == 0
    seg = sorted((tmp_path / FLIGHT_DIR).glob("[0-9]*.jsonl"))[0]
    lines = seg.read_text().splitlines()
    doctored = json.loads(lines[1])
    doctored["sql"] = "SELECT * FROM secrets"
    lines[1] = json.dumps(doctored)
    seg.write_text("\n".join(lines) + "\n")
    assert cli_main(["audit", str(tmp_path), "verify"]) == 1
    err = capsys.readouterr().err
    assert "seq 2" in err


def test_audit_export_writes_zip(tmp_path, capsys):
    _seed(tmp_path)
    out = tmp_path / "pack.zip"
    assert cli_main(["audit", str(tmp_path), "export", "--out", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 0


def test_audit_empty_workspace(tmp_path, capsys):
    cli_main(["init", str(tmp_path)])
    assert cli_main(["audit", str(tmp_path)]) == 0
    assert "No audit entries yet" in capsys.readouterr().out


def test_audit_siem_writes_ndjson_without_rows(tmp_path, capsys):
    _seed(tmp_path)
    capsys.readouterr()
    assert cli_main(["audit", str(tmp_path), "siem"]) == 0
    lines = [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert lines
    access = next(e for e in lines if e.get("type") == "access")
    assert access["decision"] == "allow"
    assert access["sql"] == "SELECT 1"
    assert "rows" not in access


def test_audit_siem_out_file(tmp_path):
    _seed(tmp_path)
    dest = tmp_path / "siem.ndjson"
    assert cli_main(["audit", str(tmp_path), "siem", "--out", str(dest)]) == 0
    lines = [json.loads(ln) for ln in dest.read_text().splitlines() if ln]
    assert any(e.get("type") == "access" for e in lines)
