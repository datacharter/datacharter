"""Data Firewall: charter parsing + live governor enforcement on the agent surface."""

import json

import pytest

from datacharter.cli import main as cli_main
from datacharter.contracts.loader import CharterError, load_charter
from datacharter.engine.session import Engine


def _write(tmp_path, firewall_line=""):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "c.csv").write_text(
        "id,email,ssn,tier\n1,a@b.com,111,pro\n2,c@d.com,222,free\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n" + firewall_line +
        "sources:\n  c:\n    type: csv\n    path: data/c.csv\n    pii:\n      c: [email, ssn]\n"
    )
    return tmp_path


def test_charter_parses_firewall_modes(tmp_path):
    assert load_charter(_write(tmp_path)).firewall_mode is None
    assert load_charter(_write(tmp_path, "firewall: block\n")).firewall_mode == "block"
    assert load_charter(_write(tmp_path, "firewall: log\n")).firewall_mode == "log"
    assert load_charter(_write(tmp_path, "firewall: on\n")).firewall_mode == "block"


def test_charter_rejects_bad_firewall(tmp_path):
    with pytest.raises(CharterError):
        load_charter(_write(tmp_path, "firewall: sometimes\n"))


async def _toolbox(ws, mode):
    charter = load_charter(ws)
    engine = Engine(ws, charter.sources).start()
    from datacharter.agent.factory import build_toolbox, detect_auto_pii

    return engine, build_toolbox(engine, charter, auto_pii=await detect_auto_pii(engine))


# email+ssn (PII +40) + to_json serialization (+25) + unbounded (+15) = 80 → high → DENY.
_HIGH_RISK = "SELECT email, ssn, to_json(c) AS blob FROM c"


@pytest.mark.asyncio
async def test_block_mode_denies_high_risk_query(tmp_path):
    ws = _write(tmp_path, "firewall: block\n")
    engine, tb = await _toolbox(ws, "block")
    try:
        out = await tb.run("query", json.dumps({"sql": _HIGH_RISK}))
        assert out.startswith("Error: the data firewall denied")
    finally:
        engine.close()


@pytest.mark.asyncio
async def test_off_mode_allows_same_query(tmp_path):
    ws = _write(tmp_path)  # firewall off
    engine, tb = await _toolbox(ws, None)
    try:
        out = await tb.run("query", json.dumps({"sql": _HIGH_RISK}))
        assert not out.startswith("Error: the data firewall")  # not blocked — it runs
    finally:
        engine.close()


@pytest.mark.asyncio
async def test_block_mode_allows_narrow_query(tmp_path):
    ws = _write(tmp_path, "firewall: block\n")
    engine, tb = await _toolbox(ws, "block")
    try:
        out = await tb.run("query", json.dumps({"sql": "SELECT tier FROM c WHERE id = 1"}))
        assert not out.startswith("Error")
    finally:
        engine.close()


def test_cmd_firewall_status_and_eval(tmp_path, capsys):
    ws = _write(tmp_path, "firewall: block\n")
    assert cli_main(["firewall", None, str(ws), "--status"]) == 0
    assert "Data Firewall: block" in capsys.readouterr().out
    # A high-risk query is BLOCKED with exit 1 under block mode.
    rc = cli_main(["firewall", "SELECT email, ssn, to_json(c) FROM c", str(ws)])
    out = capsys.readouterr().out
    assert "Data Firewall (block): BLOCKED" in out and rc == 1


def test_cmd_firewall_off_status(tmp_path, capsys):
    ws = _write(tmp_path)
    assert cli_main(["firewall", None, str(ws), "--status"]) == 0
    assert "Data Firewall: off" in capsys.readouterr().out
