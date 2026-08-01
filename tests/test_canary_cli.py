from datacharter.audit.evidence import read_entries
from datacharter.cli import main as cli_main


def test_canary_status_disabled_explains(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["canary", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "DISABLED" in out and "canary: on" in out


def _enable(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = (tmp_path / "charter.yaml").read_text()
    (tmp_path / "charter.yaml").write_text(charter + "\ncanary: on\n")


def test_canary_status_armed(tmp_path, capsys):
    _enable(tmp_path)
    assert cli_main(["canary", str(tmp_path)]) == 0
    assert "ARMED (block mode)" in capsys.readouterr().out


def test_canary_drill_writes_alarm(tmp_path, capsys):
    _enable(tmp_path)
    assert cli_main(["canary", str(tmp_path), "drill"]) == 0
    assert "Drill OK" in capsys.readouterr().out
    alarms = [e for e in read_entries(tmp_path) if e["type"] == "alarm"]
    assert len(alarms) == 1 and alarms[0]["kind"] == "canary"
    # audit surfaces it
    cli_main(["audit", str(tmp_path)])
    assert "verified" in capsys.readouterr().out


def test_canary_drill_requires_enabled(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["canary", str(tmp_path), "drill"]) == 1
