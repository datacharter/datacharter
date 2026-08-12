import json

from datacharter.contracts import load_charter
from datacharter.contracts.dbt_import import _is_pii, _sanitize_name, build_charter, import_manifest


def _manifest(**over):
    m = {
        "metadata": {"adapter_type": "snowflake"},
        "nodes": {
            "model.shop.customers": {
                "resource_type": "model", "database": "ANALYTICS", "schema": "MART",
                "name": "customers", "description": "One row per customer.",
                "columns": {
                    "id": {},
                    "email": {"meta": {"pii": True}},
                    "phone": {"tags": ["Sensitive"]},
                    "tier": {},
                },
            },
            "model.shop.orders": {
                "resource_type": "model", "database": "ANALYTICS", "schema": "MART",
                "name": "orders", "columns": {"customer_id": {}, "total": {}},
            },
        },
        "sources": {
            "source.shop.raw.signups": {
                "database": "RAW", "schema": "EVENTS", "name": "signups",
                "columns": {"ssn": {"tags": ["pii"]}, "ts": {}},
            },
        },
    }
    m.update(over)
    return m


def test_is_pii_signals():
    assert _is_pii({"meta": {"pii": True}})
    assert _is_pii({"meta": {"contains_pii": 1}})
    assert _is_pii({"meta": {"policy_tags": ["projects/x/taxonomies/y"]}})
    assert _is_pii({"tags": ["PII"]})
    assert _is_pii({"tags": ["sensitive"]})
    assert not _is_pii({"tags": ["daily"], "meta": {"pii": False}})
    assert not _is_pii({})


def test_sanitize_name():
    assert _sanitize_name("MART") == "mart"
    assert _sanitize_name("raw-events.v2") == "raw_events_v2"
    assert _sanitize_name("2020_snapshot").startswith("src_")  # can't start with a digit
    assert _sanitize_name("") == "source"


def test_build_charter_groups_and_detects():
    charter, summary = build_charter(_manifest())
    assert summary == {
        "adapter": "snowflake", "source_type": "snowflake",
        "sources": 2, "tables": 3, "pii_columns": 3, "unmapped_adapter": False,
    }
    srcs = charter["sources"]
    assert set(srcs) == {"mart", "events"}
    assert srcs["mart"]["type"] == "snowflake"
    assert srcs["mart"]["connection"]["database"] == "ANALYTICS"
    assert srcs["mart"]["tables"] == ["customers", "orders"]
    assert srcs["mart"]["pii"] == {"customers": ["email", "phone"]}  # meta.pii + tag
    assert srcs["mart"]["context"] == {"customers": "One row per customer."}
    assert srcs["events"]["pii"] == {"signups": ["ssn"]}


def test_adapter_mapping_redshift_and_unknown():
    _, s1 = build_charter({"metadata": {"adapter_type": "redshift"}, "nodes": {
        "model.a.t": {"resource_type": "model", "database": "d", "schema": "s", "name": "t"}}})
    assert s1["source_type"] == "postgres" and s1["unmapped_adapter"] is False
    _, s2 = build_charter({"metadata": {"adapter_type": "clickhouse"}, "nodes": {
        "model.a.t": {"resource_type": "model", "database": "d", "schema": "s", "name": "t"}}})
    assert s2["source_type"] == "clickhouse" and s2["unmapped_adapter"] is True


def test_generated_charter_loads(tmp_path):
    # The scaffold must be a valid charter (lenient on the ${ENV} placeholders).
    text, _ = import_manifest(_write(tmp_path, _manifest()))
    (tmp_path / "charter.yaml").write_text(text)
    charter = load_charter(tmp_path, lenient_secrets=True)
    names = {s.name for s in charter.sources}
    assert names == {"mart", "events"}
    mart = next(s for s in charter.sources if s.name == "mart")
    assert mart.pii == {"customers": ["email", "phone"]}


def test_cli_import_writes_and_guards(tmp_path, capsys):
    from datacharter.cli import main as cli

    manifest = _write(tmp_path, _manifest())
    out = tmp_path / "charter.yaml"
    assert cli(["import", "dbt", manifest, "-o", str(out)]) == 0
    assert out.exists()
    assert "3 PII column(s)" in capsys.readouterr().out
    # refuses to clobber an existing charter without --force
    assert cli(["import", "dbt", manifest, "-o", str(out)]) == 1
    assert cli(["import", "dbt", manifest, "-o", str(out), "--force"]) == 0


def test_cli_import_missing_manifest(tmp_path):
    from datacharter.cli import main as cli

    assert cli(["import", "dbt", str(tmp_path / "nope.json")]) == 1


def _write(tmp_path, manifest) -> str:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest))
    return str(p)
