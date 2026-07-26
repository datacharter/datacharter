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


def test_drift_detects_new_pii_column_and_retype(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    csv = tmp_path / "data" / "sales.csv"
    csv.write_text("id,amount\n1,10\n2,20\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  sales:\n    type: csv\n    path: data/sales.csv\n"
    )
    assert cli_main(["drift", str(tmp_path)]) == 0  # records baseline, no drift
    capsys.readouterr()
    # amount becomes float (retype) and a new email (PII) column appears
    csv.write_text("id,amount,email\n1,10.5,a@b.com\n2,20.5,c@d.com\n")
    rc = cli_main(["drift", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "email" in out and "PII" in out
    assert "retyped" in out


def test_drift_update_rebaselines(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    csv = tmp_path / "data" / "sales.csv"
    csv.write_text("id,amount\n1,10\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  sales:\n    type: csv\n    path: data/sales.csv\n"
    )
    cli_main(["drift", str(tmp_path)])  # baseline
    csv.write_text("id,amount,email\n1,10,a@b.com\n")
    assert cli_main(["drift", str(tmp_path)]) == 1  # drift
    capsys.readouterr()
    assert cli_main(["drift", str(tmp_path), "--update"]) == 0  # re-baseline
    assert cli_main(["drift", str(tmp_path)]) == 0  # clean again
