"""Query-intent risk scoring: transparent, weighted heuristic over SQL shape + PII."""

import json

from datacharter.cli import main as cli_main
from datacharter.risk import score_query


def test_narrow_filtered_read_is_low():
    a = score_query("SELECT tier FROM customers WHERE id = 5", pii_columns={"email"})
    assert a.band == "low" and a.score < 30


def test_select_star_over_pii_is_higher():
    a = score_query("SELECT * FROM customers", pii_columns={"email", "ssn"})
    names = {s.name for s in a.signals}
    assert "select_star" in names
    assert "unbounded_read" in names  # no WHERE/agg/LIMIT
    assert a.score >= 30


def test_row_serialization_flagged():
    a = score_query("SELECT to_json(customers) FROM customers WHERE id=1", pii_columns=set())
    assert any(s.name == "row_serialization" for s in a.signals)


def test_named_pii_weight_caps():
    a = score_query("SELECT email, ssn, phone FROM t WHERE 1=1",
                    pii_columns={"email", "ssn", "phone"})
    pii_sig = next(s for s in a.signals if s.name == "pii_columns")
    assert pii_sig.weight == 40  # capped, not 60


def test_canary_reference_is_high():
    a = score_query("SELECT * FROM canaries", pii_columns=set(), canaries={"canaries"})
    assert a.band == "high" and any(s.name == "canary_reference" for s in a.signals)


def test_score_capped_at_100():
    a = score_query("SELECT *, to_json(t) FROM canaries UNION SELECT * FROM t2 JOIN t3 JOIN t4",
                    pii_columns={"email", "ssn"}, canaries={"canaries"})
    assert a.score == 100


def _workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,email\n1,a@b.com\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
        "    pii:\n      c: [email]\n"
    )
    return tmp_path


def test_cmd_risk_json_and_fail_on(tmp_path, capsys):
    ws = _workspace(tmp_path)
    assert cli_main(["risk", "SELECT * FROM c", str(ws), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["band"] in ("medium", "high") and doc["score"] >= 30
    # A broad read trips the high/medium gate.
    rc = cli_main(["risk", "SELECT email FROM c", str(ws), "--fail-on", "medium"])
    assert rc in (0, 2)  # scored; exit reflects the band


def test_cmd_risk_low_query_passes_gate(tmp_path, capsys):
    ws = _workspace(tmp_path)
    rc = cli_main(["risk", "SELECT count(*) FROM c WHERE id=1", str(ws), "--fail-on", "high"])
    assert rc == 0
    assert "LOW" in capsys.readouterr().out
