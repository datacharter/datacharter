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


# -- joins + time grains (semantic layer) --------------------------------------
import duckdb  # noqa: E402

from datacharter.contracts.metrics import MetricJoin  # noqa: E402


def _duck():
    con = duckdb.connect()
    con.execute("CREATE TABLE customers AS SELECT * FROM (VALUES (1,'US'),(2,'EU')) v(id,region)")
    con.execute(
        "CREATE TABLE orders AS SELECT * FROM (VALUES "
        "(1, 10, DATE '2024-01-05'),(2, 20, DATE '2024-02-10'),(1, 5, DATE '2024-01-20')"
        ") v(customer_id, total, created_at)"
    )
    return con


def test_join_metric_runs():
    m = Metric(
        name="revenue",
        relation="orders",
        expression="sum(orders.total)",
        dimensions=["customers.region"],
        joins=[
            MetricJoin(relation="customers", on="orders.customer_id = customers.id", type="left")
        ],
    )
    rows = dict(_duck().execute(metric_sql(m)).fetchall())
    assert rows == {"US": 15, "EU": 20}


def test_time_grain_month():
    m = Metric(name="revenue", relation="orders", expression="sum(total)", time_column="created_at")
    # date_trunc returns a timestamp; key by the YYYY-MM prefix to stay type-agnostic.
    rows = {str(k)[:7]: v for k, v in _duck().execute(metric_sql(m, grain="month")).fetchall()}
    assert rows["2024-01"] == 15
    assert rows["2024-02"] == 20


def test_grain_requires_time_column():
    m = Metric(name="revenue", relation="orders", expression="sum(total)")
    with pytest.raises(MetricError):
        metric_sql(m, grain="month")


def test_bad_grain_join_type_and_injection_rejected():
    with pytest.raises(MetricError):
        metric_sql(
            Metric(name="r", relation="orders", expression="sum(total)", time_column="created_at"),
            grain="fortnight",
        )
    with pytest.raises(MetricError):
        metric_sql(
            Metric(name="r", relation="orders", expression="sum(total)",
                   joins=[MetricJoin(relation="c", on="a=b", type="cross; drop")])
        )
    with pytest.raises(MetricError):
        metric_sql(Metric(name="r", relation="orders; DROP TABLE x", expression="sum(total)"))


def test_metric_grain_cli(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "o.csv").write_text(
        "total,created_at\n10,2024-01-05\n20,2024-02-10\n5,2024-01-20\n"
    )
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  o:\n    type: csv\n    path: data/o.csv\n"
        "metrics:\n  revenue:\n    relation: o\n    expression: sum(total)\n"
        "    time_column: created_at\n"
    )
    assert cli_main(["metric", "revenue", str(tmp_path), "--grain", "month"]) == 0
    out = capsys.readouterr().out
    assert "2024-01" in out and "15" in out  # Jan bucket total


def test_grain_works_on_text_date_columns(tmp_path):
    # sqlite/CSV date columns are TEXT; date_trunc must still work (the demo's
    # placed_on is exactly this shape).
    from datacharter.cli import main as cli_main

    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["metric", "revenue", "--grain", "month", str(tmp_path)]) == 0
