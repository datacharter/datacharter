"""Continuous compliance monitor: aggregates the governance gates into one status."""

import json

from datacharter.cli import main as cli_main
from datacharter.compliance import CheckResult, ComplianceReport, render_report


def test_report_ok_ignores_skipped():
    r = ComplianceReport([
        CheckResult("a", True), CheckResult("b", True, skipped=True),
    ])
    assert r.ok is True


def test_report_fails_on_any_failed_check():
    r = ComplianceReport([CheckResult("a", True), CheckResult("b", False)])
    assert r.ok is False
    assert "FAIL" in render_report(r)


def test_monitor_on_demo_passes(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    # Fast gates only (gauntlet exercised separately); demo ships clean.
    assert cli_main(["monitor", str(tmp_path), "--no-gauntlet"]) == 0
    out = capsys.readouterr().out
    assert "contract-tests" in out and "schema-drift" in out
    assert "PASS" in out


def test_monitor_json_shape(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    capsys.readouterr()  # drain the init banner so only the JSON remains
    assert cli_main(["monitor", str(tmp_path), "--no-gauntlet", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] is True
    names = {c["name"] for c in doc["checks"]}
    assert {"contract-tests", "schema-drift", "access-plan", "gauntlet"} <= names


def test_monitor_fails_when_a_gate_fails(tmp_path, capsys):
    # A charter naming a PII column that does not exist trips the drift gate.
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,tier\n1,pro\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
        "    pii:\n      c: [email]\n"
    )
    assert cli_main(["monitor", str(tmp_path), "--no-gauntlet"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_monitor_requires_charter(tmp_path, capsys):
    assert cli_main(["monitor", str(tmp_path)]) == 1
    assert "No charter.yaml" in capsys.readouterr().err
