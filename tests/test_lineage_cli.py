"""`datacharter lineage` prints the aggregated co-read + column-lineage graph."""

import json

from datacharter.cli import main
from datacharter.engine import history


def _seed(tmp_path):
    history.record(
        tmp_path,
        "q1",
        1,
        {"relations": ["orders", "customers"], "lineage": {"contact": ["customers.email"]}},
    )


def test_lineage_text(tmp_path, capsys):
    _seed(tmp_path)
    assert main(["lineage", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "orders" in out and "customers" in out


def test_lineage_json(tmp_path, capsys):
    _seed(tmp_path)
    assert main(["lineage", str(tmp_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["relations"]["orders"]["co_read"]["customers"] == 1


def test_lineage_empty(tmp_path, capsys):
    assert main(["lineage", str(tmp_path)]) == 0
    assert "No query history" in capsys.readouterr().out
