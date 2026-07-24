from datacharter.cli import main as cli_main


def test_drift_clean_on_demo(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["drift", str(tmp_path)]) == 0
    assert "No schema drift" in capsys.readouterr().out


def test_drift_flags_missing_pii_column(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,tier\n1,pro\n2,free\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  c:\n"
        "    type: csv\n"
        "    path: data/c.csv\n"
        "    pii:\n"
        "      c:\n"
        "        - email\n"
    )
    assert cli_main(["drift", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "email" in out
    assert "masking gap" in out


def test_drift_requires_charter(tmp_path, capsys):
    assert cli_main(["drift", str(tmp_path)]) == 1
    assert "No charter.yaml" in capsys.readouterr().err
