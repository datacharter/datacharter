import pytest

from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.contracts.metrics import Metric, MetricError, metric_sql


def test_metric_sql_no_dimensions():
    m = Metric(name="order_count", relation="orders", expression="count(*)")
    assert metric_sql(m) == "SELECT count(*) AS order_count FROM orders"


def test_metric_sql_with_dimensions():
    m = Metric(
        name="revenue", relation="orders", expression="sum(total)", dimensions=["customer_id"]
    )
    assert metric_sql(m) == (
        "SELECT customer_id, sum(total) AS revenue FROM orders "
        "GROUP BY customer_id ORDER BY customer_id"
    )


def test_metric_sql_by_override():
    m = Metric(name="revenue", relation="orders", expression="sum(total)")
    assert "GROUP BY region" in metric_sql(m, by=["region"])


def test_metric_sql_rejects_bad_relation():
    with pytest.raises(MetricError):
        metric_sql(Metric(name="x", relation="orders; DROP", expression="count(*)"))


def test_charter_loads_metrics(tmp_path):
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n  o:\n    type: parquet\n    path: o.parquet\n"
        "metrics:\n  rev:\n    relation: o\n    expression: sum(total)\n    dimensions: [region]\n"
    )
    charter = load_charter(tmp_path)
    assert charter.metrics[0].name == "rev"
    assert charter.metrics[0].dimensions == ["region"]


def test_metric_cli_runs(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = tmp_path / "charter.yaml"
    charter.write_text(
        charter.read_text()
        + "\nmetrics:\n  order_count:\n    relation: store.orders\n    expression: count(*)\n"
    )
    assert cli_main(["metric", "order_count", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "order_count" in out
    assert "90" in out  # 90 demo orders


def test_metric_cli_unknown(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["metric", "nope", str(tmp_path)]) == 1
    assert "No metric" in capsys.readouterr().err
