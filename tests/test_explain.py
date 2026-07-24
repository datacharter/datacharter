from datacharter.cli import main as cli_main


def test_explain_shows_plan_without_running(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    sql = "SELECT customer_id, count(*) FROM store.orders GROUP BY customer_id"
    assert cli_main(["explain", sql, str(tmp_path)]) == 0
    assert "rows" in capsys.readouterr().out.lower()  # plan carries "~N rows" estimates


def test_explain_rejects_non_select(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["explain", "DELETE FROM store.orders", str(tmp_path)]) == 1
    assert "Explain failed" in capsys.readouterr().err
