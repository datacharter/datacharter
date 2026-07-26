from datacharter.cli import main as cli_main
from datacharter.contracts.pii import classify_pii, detect_value_pii


def test_flags_direct_identifiers():
    cols = ["id", "email", "customer_phone", "first_name", "ssn", "created_at"]
    assert classify_pii(cols) == ["email", "customer_phone", "first_name", "ssn"]


def test_ignores_generic_columns():
    assert classify_pii(["product_name", "order_count", "total", "region", "ship_id"]) == []


def test_case_insensitive():
    assert classify_pii(["Email", "SSN"]) == ["Email", "SSN"]


def test_scan_suggests_email_on_demo(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["scan", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "customers" in out
    assert "email" in out


def test_scan_requires_charter(tmp_path, capsys):
    assert cli_main(["scan", str(tmp_path)]) == 1
    assert "No charter.yaml" in capsys.readouterr().err


def test_detect_value_pii_email_and_ssn():
    assert detect_value_pii(["a@b.com", "c@d.org", "e@f.io"]) == "email"
    assert detect_value_pii(["123-45-6789", "987-65-4321", "111-22-3333"]) == "ssn"


def test_detect_value_pii_ignores_ids_and_small_samples():
    assert detect_value_pii([1, 2, 3, 4, 5]) is None
    assert detect_value_pii(["a@b.com"]) is None  # too few samples to be confident


def test_detect_value_pii_credit_card_luhn():
    # Luhn-valid test card numbers (with and without separators).
    cards = ["4539578763621486", "4485 2757 0510 1990", "6011-0009-9013-9424"]
    assert detect_value_pii(cards) == "credit_card"


def test_detect_value_pii_phone_requires_formatting():
    phones = ["555-123-4567", "(555) 987-6543", "+1 555 111 2222"]
    assert detect_value_pii(phones) == "phone"


def test_detect_value_pii_bare_numeric_ids_not_phone_or_card():
    # bare digit strings (ids) must NOT be flagged as phone (no separators) or card (fails Luhn/len)
    assert detect_value_pii(["1001", "1002", "1003", "1004"]) is None
    assert detect_value_pii(["100000001", "100000002", "100000003"]) is None


def test_scan_detects_pii_by_value(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "leads.csv").write_text("contact,score\na@b.com,1\nc@d.com,2\ne@f.com,3\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  leads:\n    type: csv\n    path: data/leads.csv\n"
    )
    assert cli_main(["scan", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "contact" in out  # value-detected even though the column name isn't PII


def test_scan_write_merges_pii(tmp_path):
    from datacharter.contracts import load_charter

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "leads.csv").write_text("email,score\na@b.com,1\nc@d.com,2\ne@f.com,3\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  leads:\n    type: csv\n    path: data/leads.csv\n"
    )
    assert cli_main(["scan", str(tmp_path), "--write"]) == 0
    assert load_charter(tmp_path).sources[0].pii == {"leads": ["email"]}


def test_set_pii_preserves_credential_refs(tmp_path):
    from datacharter.contracts.writer import set_pii

    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  wh:\n"
        "    type: postgres\n"
        "    connection:\n"
        "      host: db\n"
        "      database: d\n"
        "      user: u\n"
        "    credentials:\n"
        "      password: ${WH_PW}\n"
        "    tables: [customers]\n"
    )
    set_pii(tmp_path, "wh", "customers", ["email"])
    text = (tmp_path / "charter.yaml").read_text()
    assert "${WH_PW}" in text  # credential ref preserved (D7)
    assert "email" in text
