"""Self-writing guides: predicate mining, thresholds, dedup, apply."""


from datacharter.contracts.suggest import apply_suggestions, mine_history, render_suggestions
from datacharter.engine.history import record


def _seed(ws, sqls_relations):
    for sql, rels in sqls_relations:
        record(ws, sql, 1, {"relations": rels, "columns": [], "lineage": {}})


def test_recurring_predicate_suggested(tmp_path):
    runs = [("SELECT sum(amount) FROM sales WHERE refunded = false", ["sales"])] * 4
    runs += [("SELECT count(*) FROM sales", ["sales"])]
    _seed(tmp_path, runs)
    s = mine_history(tmp_path)
    filt = [x for x in s if x.kind == "filter"]
    assert len(filt) == 1
    assert "refunded = false" in filt[0].text
    assert filt[0].count == 4 and filt[0].total == 5


def test_below_threshold_not_suggested(tmp_path):
    runs = [("SELECT 1 FROM sales WHERE refunded = false", ["sales"])] * 2
    runs += [("SELECT count(*) FROM sales", ["sales"])] * 8
    _seed(tmp_path, runs)  # 2 of 10 = 20% < 40% and count 2 < 3
    assert [x for x in mine_history(tmp_path) if x.kind == "filter"] == []


def test_unparseable_sql_skipped(tmp_path):
    _seed(tmp_path, [("NOT REALLY SQL AT ALL", ["sales"])] * 5)
    assert [x for x in mine_history(tmp_path) if x.kind == "filter"] == []


def test_join_cooccurrence(tmp_path):
    _seed(tmp_path, [("SELECT 1", ["crm.customers", "sales.orders"])] * 3)
    joins = [x for x in mine_history(tmp_path) if x.kind == "join"]
    assert len(joins) == 1 and "queried together" in joins[0].text


def test_dedup_against_existing_guides(tmp_path):
    (tmp_path / "guides").mkdir()
    (tmp_path / "guides" / "notes.md").write_text(
        "Always filter refunded = false on sales."
    )
    _seed(tmp_path, [("SELECT 1 FROM sales WHERE refunded = false", ["sales"])] * 5)
    assert [x for x in mine_history(tmp_path) if x.kind == "filter"] == []


def test_apply_writes_and_next_mine_is_quiet(tmp_path):
    _seed(tmp_path, [("SELECT 1 FROM sales WHERE region != 'ZZ'", ["sales"])] * 5)
    s = mine_history(tmp_path)
    assert s
    path = apply_suggestions(tmp_path, s)
    assert "region != 'ZZ'" in path.read_text()
    assert mine_history(tmp_path) == []  # now covered → quiet
    assert "already cover" in render_suggestions([])


def test_numeric_and_flipped_comparisons(tmp_path):
    _seed(tmp_path, [("SELECT 1 FROM t WHERE 10 < amount", ["t"])] * 4)
    s = [x for x in mine_history(tmp_path) if x.kind == "filter"]
    assert s and "amount > 10" in s[0].text
