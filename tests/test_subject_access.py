"""Subject-access receipts (DSAR): masked cross-relation lookup, signed + verifiable."""

import json

from datacharter.cli import main as cli_main
from datacharter.provenance import keys, receipt
from datacharter.provenance.subject import find_relations_with_column, subject_query


def test_sql_literal_escapes_quotes():
    assert subject_query("t", "email", "a'b@x.com").endswith("= 'a''b@x.com'")


def test_find_relations_skips_scratch_schemas():
    idx = {"database": 0, "name": 1, "column_names": 2}
    rows = [
        ["store", "customers", ["id", "email"]],
        ["local", "canaries", ["email"]],      # scratch — skipped
        ["memory", "orders", ["customer_id"]],  # no email — skipped
    ]
    found = find_relations_with_column(rows, idx, "email")
    assert found == [("store.customers", ["id", "email"])]


def _workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text(
        "id,email,tier\n1,alice@x.com,pro\n2,bob@y.com,free\n3,alice@x.com,free\n"
    )
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
        "    pii:\n      c: [email]\n"
    )
    return tmp_path


def test_subject_access_requires_key(tmp_path, capsys):
    ws = _workspace(tmp_path)
    assert cli_main(["subject-access", "alice@x.com", str(ws)]) == 1
    assert "keygen" in capsys.readouterr().err


def test_subject_access_receipt_masks_and_verifies(tmp_path, capsys):
    ws = _workspace(tmp_path)
    cli_main(["provenance", "keygen", str(ws)])
    capsys.readouterr()
    out = tmp_path / "dsar.json"
    assert cli_main(["subject-access", "alice@x.com", str(ws), "-o", str(out)]) == 0

    r = json.loads(out.read_text())
    body = r["body"]
    assert body["schema"] == "datacharter/subject-access/v1"
    assert body["subject"] == {"column": "email", "value": "alice@x.com"}
    assert body["total_matched_rows"] == 2  # two alice rows, bob excluded
    rec = body["records"][0]
    # The subject's own key column is masked — the receipt shows what the AGENT sees.
    assert rec["rows"][0]["email"] == "•••"
    assert rec["rows"][0]["tier"] in ("pro", "free")  # non-PII passes through

    # The DSAR is a real provenance receipt: signature + content hash verify offline.
    v = receipt.verify(r)
    assert v["ok"] is True


def test_subject_access_masks_auto_detected_pii(tmp_path, capsys):
    # `contact` is an emails column NOT declared PII — the agent surface auto-masks
    # it, so the DSAR must too (audit P1).
    (tmp_path / "data").mkdir()
    rows = "id,contact\nalice,alice@corp.example\n" + "\n".join(
        f"u{i},user{i}@corp.example" for i in range(8))
    (tmp_path / "data" / "c.csv").write_text(rows)
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n")
    cli_main(["provenance", "keygen", str(tmp_path)])
    capsys.readouterr()
    out = tmp_path / "d.json"
    assert cli_main(["subject-access", "alice@corp.example", str(tmp_path),
                     "--column", "contact", "-o", str(out)]) == 0
    body = json.loads(out.read_text())["body"]
    rec = body["records"][0]
    assert "contact" in rec["masked_columns"]  # auto-detected PII is masked
    assert all(row["contact"] == "•••" for row in rec["rows"])  # raw value never in the rows


def test_subject_access_no_double_count_through_flat_views(tmp_path, capsys):
    # A multi-table source registers store.customers AND the memory store__customers
    # alias; the subject must be counted once (QA flag #4).
    (tmp_path / "store.db")  # sqlite path; build via the demo instead
    cli_main(["init", str(tmp_path), "--demo"])
    cli_main(["provenance", "keygen", str(tmp_path)])
    capsys.readouterr()
    out = tmp_path / "d.json"
    assert cli_main(["subject-access", "ada@example.com", str(tmp_path), "-o", str(out)]) == 0
    import json as _j

    body = _j.loads(out.read_text())["body"]
    relations = [r["relation"] for r in body["records"]]
    assert not any("__" in r for r in relations)  # flat alias excluded
    assert body["total_matched_rows"] == 1  # counted once, not twice


def test_subject_access_signed_by_workspace_key(tmp_path, capsys):
    ws = _workspace(tmp_path)
    cli_main(["provenance", "keygen", str(ws)])
    capsys.readouterr()
    cli_main(["subject-access", "bob@y.com", str(ws), "-o", str(tmp_path / "d.json")])
    r = json.loads((tmp_path / "d.json").read_text())
    signer = keys.load_signer(ws)
    assert r["signature"]["key_id"] == signer.key_id
    assert r["body"]["total_matched_rows"] == 1
