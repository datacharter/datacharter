from datacharter.cli import main as cli_main


def test_sample_masks_pii(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["sample", "store.customers", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "email" in out  # header present
    assert "•••" in out  # PII values masked
    assert "ada@example.com" not in out  # raw PII not leaked


def test_sample_shows_non_pii(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    cli_main(["sample", "store.customers", str(tmp_path)])
    out = capsys.readouterr().out
    assert "pro" in out or "free" in out  # tier column (non-PII) is shown in the clear


def test_sample_rejects_bad_relation(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["sample", "x; DROP", str(tmp_path)]) == 1
    assert "Invalid relation" in capsys.readouterr().err
