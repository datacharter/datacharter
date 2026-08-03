"""CLI: `query` runs ad-hoc read-only SQL; `snapshot` routes through snapshot_sync."""

import json

from datacharter.cli import main


def test_query_json_format(tmp_path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    capsys.readouterr()  # drain init output
    rc = main(["query", "SELECT 1 AS n, 'x' AS s", str(tmp_path), "--format", "json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out) == [{"n": 1, "s": "x"}]


def test_query_csv_format(tmp_path, capsys):
    main(["init", str(tmp_path)])
    capsys.readouterr()  # drain init output
    assert main(["query", "SELECT 1 AS a, 2 AS b", str(tmp_path), "--format", "csv"]) == 0
    out = capsys.readouterr().out
    assert "a,b" in out and "1,2" in out


def test_query_rejects_writes(tmp_path):
    main(["init", str(tmp_path)])
    assert main(["query", "DROP TABLE x", str(tmp_path)]) == 1


def test_snapshot_uses_snapshot_sync(tmp_path, monkeypatch):
    main(["init", str(tmp_path), "--demo"])
    calls = {}

    from datacharter.engine.session import Engine

    real = Engine.snapshot_sync

    def spy(self, sql, name):
        calls["args"] = (sql, name)
        return real(self, sql, name)

    monkeypatch.setattr(Engine, "snapshot_sync", spy)
    rc = main(["snapshot", "top", "SELECT 1 AS n", str(tmp_path)])
    assert rc == 0
    assert calls["args"] == ("SELECT 1 AS n", "top")


def test_demo_exposes_flat_views_as_quickstart_teaches(tmp_path, capsys):
    # The quickstart teaches `source__table` names; the demo workspace must
    # actually have them (it didn't, when its charter omitted `tables:`).
    from datacharter.cli import main as cli_main

    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["query", "SELECT count(*) AS n FROM store__customers", str(tmp_path)]) == 0
    assert "3" in capsys.readouterr().out
