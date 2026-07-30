from datacharter.contracts.guides import find_pii_in_text, scan_guides_for_pii


def test_find_pii_in_text_flags_email_and_ssn():
    hits = find_pii_in_text("Contact ada@volt.dev or use SSN 123-45-6789 for lookups.")
    kinds = {h.split(":")[0] for h in hits}
    assert "email" in kinds
    assert "ssn" in kinds


def test_find_pii_in_text_clean_returns_empty():
    assert find_pii_in_text("Net revenue excludes refunds; exclude tier = 'internal'.") == []


def test_find_pii_ipv4_and_credit_card():
    hits = find_pii_in_text("server 10.0.0.5 card 4111-1111-1111-1111")
    kinds = {h.split(":")[0] for h in hits}
    assert "ipv4" in kinds
    assert "credit_card" in kinds


def test_scan_guides_flags_pii_file(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    (g / "clean.md").write_text("Use net revenue; exclude test accounts.")
    (g / "leaky.md").write_text("Example customer: grace@arc.io, SSN 111-22-3333.")
    hits = scan_guides_for_pii(tmp_path)
    assert "clean" not in hits
    assert "leaky" in hits
    assert any("email" in h for h in hits["leaky"])


def test_scan_guides_ignores_html_comments(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    # PII only inside a comment never reaches the model, so it must not be flagged.
    (g / "commented.md").write_text("<!-- old note: bob@x.io -->\nUse net revenue.")
    assert scan_guides_for_pii(tmp_path) == {}


def test_scan_guides_no_dir(tmp_path):
    assert scan_guides_for_pii(tmp_path) == {}


def test_scan_cli_flags_guide_pii_and_strict_exit(tmp_path, capsys):
    from datacharter.cli import main as cli_main

    cli_main(["init", str(tmp_path), "--demo"])
    (tmp_path / "guides").mkdir(exist_ok=True)
    (tmp_path / "guides" / "leaky.md").write_text("Example: ada@volt.dev")
    # default: warns but exits 0
    assert cli_main(["scan", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Literal PII" in out and "ada@volt.dev" in out
    # --strict: exits non-zero
    assert cli_main(["scan", str(tmp_path), "--strict"]) == 1
