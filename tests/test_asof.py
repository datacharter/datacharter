"""Governance time-travel: the agent surface as of a git ref, and a query masked
by that ref's PII rules against current data."""

import subprocess

from datacharter.cli import main as cli_main


def _git(ws, *args):
    subprocess.run(["git", *args], cwd=ws, check=True, capture_output=True)


def _commit_charter(ws, text, msg):
    (ws / "charter.yaml").write_text(text)
    _git(ws, "add", "charter.yaml")
    _git(ws, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", msg)


_V1 = (
    "version: 1\nsources:\n  crm:\n    type: csv\n    path: data/c.csv\n"
    "    tables: [c]\n"
)
_V2 = (  # v2 adds email as PII
    "version: 1\nsources:\n  crm:\n    type: csv\n    path: data/c.csv\n"
    "    tables: [c]\n    pii:\n      c: [email]\n"
)


def _workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,email\n1,a@b.com\n2,c@d.com\n")
    _git(tmp_path, "init")
    return tmp_path


def test_asof_surface_snapshot_reflects_old_rules(tmp_path, capsys):
    ws = _workspace(tmp_path)
    _commit_charter(ws, _V1, "v1: no pii")
    _commit_charter(ws, _V2, "v2: email pii")
    # As of the first commit, email was NOT masked.
    assert cli_main(["asof", "HEAD~1", str(ws)]) == 0
    out = capsys.readouterr().out
    assert "as of HEAD~1" in out
    assert "masked[—]" in out  # no PII declared then


def test_asof_surface_snapshot_current_rules(tmp_path, capsys):
    ws = _workspace(tmp_path)
    _commit_charter(ws, _V1, "v1")
    _commit_charter(ws, _V2, "v2")
    assert cli_main(["asof", "HEAD", str(ws)]) == 0
    assert "masked[email]" in capsys.readouterr().out


def test_asof_query_masks_by_ref_rules(tmp_path, capsys):
    ws = _workspace(tmp_path)
    _commit_charter(ws, _V1, "v1")
    _commit_charter(ws, _V2, "v2")
    # Under HEAD (email is PII), the query result masks email.
    assert cli_main(["asof", "HEAD", str(ws), "--query", "SELECT id, email FROM crm"]) == 0
    out = capsys.readouterr().out
    assert "a@b.com" not in out and "•••" in out
    # Under HEAD~1 (email not yet PII), the same query shows raw email.
    assert cli_main(["asof", "HEAD~1", str(ws), "--query", "SELECT id, email FROM crm"]) == 0
    assert "a@b.com" in capsys.readouterr().out


def test_asof_json_snapshot(tmp_path, capsys):
    import json

    ws = _workspace(tmp_path)
    _commit_charter(ws, _V2, "v2")
    assert cli_main(["asof", "HEAD", str(ws), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ref"] == "HEAD"
    assert "surface_hash" in doc and doc["surface"]["sources"]["crm"]


def test_asof_missing_ref_errors(tmp_path, capsys):
    ws = _workspace(tmp_path)
    _commit_charter(ws, _V1, "v1")
    assert cli_main(["asof", "does-not-exist", str(ws)]) == 1
    assert "could not be resolved" in capsys.readouterr().err
