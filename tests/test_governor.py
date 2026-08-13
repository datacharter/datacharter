"""The Reasoning Governor: graduated decisions from intent + purpose + sensitivity."""

from datacharter.cli import main as cli_main
from datacharter.governor import Action, govern


def test_narrow_read_is_allowed():
    d = govern("SELECT tier FROM t WHERE id = 1", pii_columns={"email"})
    assert d.action == Action.ALLOW


def test_canary_reference_is_denied():
    d = govern("SELECT * FROM canaries", canaries={"canaries"})
    assert d.action == Action.DENY and "honeytoken" in d.reason


def test_high_risk_is_denied():
    d = govern("SELECT *, to_json(t) FROM canaries JOIN a JOIN b",
               pii_columns={"email", "ssn"}, canaries={"canaries"})
    assert d.action == Action.DENY


def test_export_purpose_over_pii_is_denied():
    d = govern("SELECT email FROM t WHERE id=1", pii_columns={"email"}, purpose="export")
    assert d.action == Action.DENY and "export" in d.reason


def test_serialization_forces_mask_more():
    d = govern("SELECT to_json(t) FROM t WHERE id=1", pii_columns=set())
    assert d.action == Action.MASK_MORE


def test_aggregate_over_pii_adds_noise():
    d = govern("SELECT count(email) FROM t WHERE tier='pro'", pii_columns={"email"})
    assert d.action == Action.ADD_NOISE and "dp" in d.recommendation


def test_medium_risk_steps_up():
    # Naming two PII columns in a filtered, non-aggregate read → medium band → step up.
    d = govern("SELECT email, ssn FROM t WHERE id = 1", pii_columns={"email", "ssn"})
    assert d.action == Action.STEP_UP


def _workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,email\n1,a@b.com\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
        "    pii:\n      c: [email]\n"
    )
    return tmp_path


def test_cmd_govern_allow_and_deny(tmp_path, capsys):
    ws = _workspace(tmp_path)
    assert cli_main(["govern", "SELECT count(*) FROM c WHERE id=1", str(ws)]) == 0
    assert "ALLOW" in capsys.readouterr().out
    rc = cli_main(["govern", "SELECT email FROM c", str(ws), "--purpose", "export"])
    assert rc == 1
    assert "DENY" in capsys.readouterr().out


def test_select_star_over_pii_export_is_denied():
    # SELECT * names no PII but exposes it — export purpose must still DENY (audit P2).
    d = govern("SELECT * FROM customers", pii_columns={"email"}, purpose="export")
    assert d.action == Action.DENY


def test_export_purpose_phrase_matches():
    d = govern("SELECT email FROM t WHERE id=1", pii_columns={"email"},
               purpose="export data to a vendor")
    assert d.action == Action.DENY  # word-aware, not just the bare keyword


def test_naming_pii_directly_steps_up():
    # A narrow, low-score PII read still steps up (the promise: naming PII → step-up).
    d = govern("SELECT email FROM t WHERE email = 'x'", pii_columns={"email"})
    assert d.action == Action.STEP_UP


def test_no_pii_narrow_read_allowed():
    d = govern("SELECT tier FROM t WHERE id = 1", pii_columns={"email"})
    assert d.action == Action.ALLOW


def test_cmd_govern_json(tmp_path, capsys):
    import json

    ws = _workspace(tmp_path)
    assert cli_main(["govern", "SELECT count(email) FROM c", str(ws), "--json"]) == 2
    doc = json.loads(capsys.readouterr().out)
    assert doc["action"] == "add_noise" and "risk" in doc


def test_cmd_govern_runs_on_uncredentialed_charter(tmp_path, capsys):
    # govern is metadata-only; must not require resolvable ${ENV} creds (audit P1).
    cli_main(["init", str(tmp_path), "--template", "secure"])
    capsys.readouterr()
    rc = cli_main(["govern", "SELECT tier FROM crm.customers WHERE id=1", str(tmp_path)])
    assert rc in (0, 2)  # ran without crashing on unresolved credentials
    assert "Decision" in capsys.readouterr().out
