from datacharter.cli import main as cli_main
from datacharter.engine.history import record


def _seed(ws):
    cli_main(["init", str(ws), "--demo"])
    for _ in range(5):
        record(ws, "SELECT 1 FROM sales WHERE refunded = false", 1,
               {"relations": ["sales"], "columns": [], "lineage": {}})


def test_suggest_prints_and_applies(tmp_path, capsys):
    _seed(tmp_path)
    assert cli_main(["suggest", str(tmp_path)]) == 0
    assert "refunded = false" in capsys.readouterr().out
    assert cli_main(["suggest", str(tmp_path), "--apply"]) == 0
    out = capsys.readouterr().out
    assert "Appended" in out
    assert (tmp_path / "guides" / "suggested.md").exists()
    # applied → next run is quiet
    assert cli_main(["suggest", str(tmp_path)]) == 0
    assert "already cover" in capsys.readouterr().out
