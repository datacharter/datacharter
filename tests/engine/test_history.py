"""Local query history store + lineage aggregation."""

from datacharter.engine import history


def test_record_then_read_newest_first(tmp_path):
    history.record(tmp_path, "SELECT 1", 1, None)
    history.record(tmp_path, "SELECT 2", 2, {"relations": ["a"], "columns": ["a.x"]})
    rows = history.read_history(tmp_path, limit=10)
    assert [r["sql"] for r in rows] == ["SELECT 2", "SELECT 1"]
    assert rows[0]["row_count"] == 2 and rows[0]["relations"] == ["a"]


def test_history_capped_at_500(tmp_path):
    for i in range(520):
        history.record(tmp_path, f"SELECT {i}", i, None)
    lines = (tmp_path / ".datacharter" / "history.jsonl").read_text().splitlines()
    assert len(lines) == 500
    assert history.read_history(tmp_path, limit=1)[0]["sql"] == "SELECT 519"


def test_lineage_folds_provenance(tmp_path):
    history.record(
        tmp_path,
        "q1",
        1,
        {
            "relations": ["orders", "customers"],
            "columns": [],
            "lineage": {"contact": ["customers.email"]},
        },
    )
    history.record(tmp_path, "q2", 1, {"relations": ["orders", "customers"], "columns": []})
    g = history.lineage(tmp_path)
    assert g["relations"]["orders"]["co_read"]["customers"] == 2
    assert g["columns"]["contact"] == ["customers.email"]


def test_read_history_empty_when_absent(tmp_path):
    assert history.read_history(tmp_path) == []
    assert history.lineage(tmp_path) == {"relations": {}, "columns": {}}
