"""Self-Defending Data: signed envelope, tamper-evidence, TTL self-redaction."""

import json
from datetime import datetime, timedelta, timezone

from datacharter.cli import main as cli_main
from datacharter.provenance import keys
from datacharter.selfdefend import REDACTED, build_envelope, open_envelope


def _signer(tmp_path):
    return keys.generate(tmp_path)


def test_open_valid_envelope(tmp_path):
    s = _signer(tmp_path)
    env = build_envelope(workspace="w", surface_hash="h", columns=["id", "email"],
                         rows=[[1, "•••"]], masked_columns=["email"], signer=s, ttl_seconds=None)
    opened = open_envelope(env)
    assert opened["ok"] and not opened["tampered"] and not opened["expired"]
    assert opened["rows"] == [[1, "•••"]]


def test_tamper_is_detected(tmp_path):
    s = _signer(tmp_path)
    env = build_envelope(workspace="w", surface_hash="h", columns=["id"], rows=[[1]],
                         masked_columns=[], signer=s, ttl_seconds=None)
    env["body"]["data"]["rows"] = [[999]]  # forge a value after signing
    opened = open_envelope(env)
    assert opened["tampered"] and not opened["ok"] and opened["rows"] == []


def test_expiry_self_redacts(tmp_path):
    s = _signer(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    env = build_envelope(workspace="w", surface_hash="h", columns=["id", "email"],
                         rows=[[1, "•••"]], masked_columns=["email"], signer=s,
                         ttl_seconds=60, issued_at=past)
    opened = open_envelope(env)
    assert opened["expired"] and not opened["ok"]
    assert opened["rows"] == [[REDACTED, REDACTED]]  # every cell self-redacted


def test_not_yet_expired(tmp_path):
    s = _signer(tmp_path)
    env = build_envelope(workspace="w", surface_hash="h", columns=["id"], rows=[[1]],
                         masked_columns=[], signer=s, ttl_seconds=3600)
    opened = open_envelope(env, now=datetime.now(timezone.utc))
    assert opened["ok"] and not opened["expired"]


def _workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,email,tier\n1,a@b.com,pro\n2,c@d.com,free\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
        "    pii:\n      c: [email]\n"
    )
    return tmp_path


def test_cmd_seal_and_open_roundtrip(tmp_path, capsys):
    ws = _workspace(tmp_path)
    cli_main(["provenance", "keygen", str(ws)])
    capsys.readouterr()
    out = ws / "env.json"
    assert cli_main(["seal-data", "SELECT id, email FROM c", str(ws), "-o", str(out)]) == 0
    capsys.readouterr()
    # The sealed payload never contains the raw email.
    assert "a@b.com" not in out.read_text()
    assert cli_main(["open-data", str(out)]) == 0
    body = capsys.readouterr().out
    assert "•••" in body and "a@b.com" not in body


def test_cmd_open_detects_tamper(tmp_path, capsys):
    ws = _workspace(tmp_path)
    cli_main(["provenance", "keygen", str(ws)])
    capsys.readouterr()
    out = ws / "env.json"
    cli_main(["seal-data", "SELECT id, tier FROM c", str(ws), "-o", str(out)])
    capsys.readouterr()
    env = json.loads(out.read_text())
    env["body"]["data"]["rows"][0][1] = "hacked"
    out.write_text(json.dumps(env))
    assert cli_main(["open-data", str(out)]) == 1
    assert "TAMPERED" in capsys.readouterr().err
