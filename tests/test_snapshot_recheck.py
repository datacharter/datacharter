from datacharter.cli import main as cli_main


def test_snapshot_then_recheck_unchanged(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    sql = "SELECT count(*) AS n FROM store.customers"
    assert cli_main(["snapshot", "cust", sql, str(tmp_path)]) == 0
    assert cli_main(["recheck", "cust", str(tmp_path)]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_recheck_detects_change(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["snapshot", "answer", "SELECT 1 AS n", str(tmp_path)]) == 0
    # the query now returns something different than what was snapshotted
    (tmp_path / ".datacharter" / "snapshots" / "answer.sql").write_text("SELECT 2 AS n")
    assert cli_main(["recheck", "answer", str(tmp_path)]) == 1
    assert "CHANGED" in capsys.readouterr().out


def test_recheck_without_snapshot(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["recheck", "nope", str(tmp_path)]) == 1
    assert "No snapshot" in capsys.readouterr().err


def test_snapshot_rejects_bad_name(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["snapshot", "bad; drop", "SELECT 1", str(tmp_path)]) == 1
    assert "Invalid snapshot name" in capsys.readouterr().err
