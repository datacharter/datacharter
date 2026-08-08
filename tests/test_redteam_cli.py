"""The Gauntlet — governance self-attack, scored through the real ToolBox."""

from __future__ import annotations

from datacharter.agent.redteam import ATTACKS, Attack, GauntletReport, _judge
from datacharter.audit.canary import CanaryGuard
from datacharter.audit.evidence import read_entries
from datacharter.cli import main as cli_main


def test_redteam_demo_all_withstood(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    rc = cli_main(["redteam", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Governance holds" in out
    assert "attacks withstood" in out


def test_redteam_is_ci_gate_clean(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["redteam", str(tmp_path)]) == 0  # exit 0 = no breach


def test_redteam_records_to_chain(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    cli_main(["redteam", str(tmp_path)])
    sessions = [e for e in read_entries(tmp_path) if e.get("type") == "session"]
    assert any(s["surface"] == "redteam" for s in sessions)
    cli_main(["audit", str(tmp_path)])
    assert "verified" in capsys.readouterr().out


def test_redteam_exercises_policies(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = (tmp_path / "charter.yaml").read_text()
    (tmp_path / "charter.yaml").write_text(
        charter + "\npolicies:\n  store.customers:\n    - aggregates only\n"
    )
    rc = cli_main(["redteam", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Policy evasion" in out  # the category ran (policy active)


def test_oracle_detects_leak():
    """Feed the oracle a fabricated output containing a sentinel — it must fail."""
    guard = CanaryGuard(tokens=["canary-deadbeef"], mode="log")
    leaked = '{"columns": ["email"], "rows": [["canary-deadbeef@tripwire.invalid"]]}'
    attack = Attack("PII exfiltration", "SELECT email FROM local.canaries", "mask", "x")
    finding = _judge(attack, leaked, guard)
    assert finding is not None and "honeytoken" in finding


def test_oracle_passes_masked_output():
    guard = CanaryGuard(tokens=["canary-deadbeef"], mode="log")
    masked = '{"columns": ["email"], "rows": [["\\u2022\\u2022\\u2022"]]}'
    attack = Attack("PII exfiltration", "SELECT email FROM local.canaries", "mask", "x")
    assert _judge(attack, masked, guard) is None


def test_oracle_flags_unrefused_write():
    guard = CanaryGuard(tokens=["canary-x"], mode="log")
    attack = Attack("Read-only bypass", "DROP TABLE x", "refuse", "x")
    # A non-error response to a write attack is a breach.
    assert _judge(attack, '{"rows": [[1]]}', guard) is not None
    # An error response withstands.
    assert _judge(attack, "Error: not allowed", guard) is None


def test_report_ok_only_when_no_findings():
    r = GauntletReport()
    r.by_category["x"] = (3, 3)
    assert r.ok
    r.findings.append("something broke")
    assert not r.ok


def test_attack_corpus_is_nonempty_and_typed():
    assert len(ATTACKS) >= 15
    assert all(a.expect in ("refuse", "mask") for a in ATTACKS)
