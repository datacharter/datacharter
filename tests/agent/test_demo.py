import asyncio

from datacharter.agent import demo
from datacharter.agent.factory import build_toolbox, detect_auto_pii
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def _box(ws):
    charter = load_charter(ws)
    engine = Engine(ws, charter.sources).start()
    box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)))
    return engine, box


def test_narrate_shows_masking_diff_and_readonly(tmp_path):
    ws = tmp_path / "ws"
    cli_main(["init", str(ws), "--demo"])
    engine, box = _box(ws)
    try:
        text = "\n".join(asyncio.run(demo.narrate(box, engine)))
    finally:
        engine.close()
    assert "•••" in text  # the agent sees the email masked
    assert "ada@example.com" in text  # ...shown next to the raw value it never sees
    assert "masked columns: email" in text
    assert "read-only" in text.lower()
    assert "Error:" in text  # the DROP was refused, not silently ignored


def test_run_scaffolds_a_throwaway_and_exits_zero(capsys):
    rc = demo.run(None)  # no directory → scaffold a throwaway demo
    out = capsys.readouterr().out
    assert rc == 0
    assert "PII masking" in out and "•••" in out
    assert "datacharter serve" in out
    assert "safe to delete" in out


def test_run_uses_an_existing_workspace(tmp_path, capsys):
    ws = tmp_path / "ws"
    cli_main(["init", str(ws), "--demo"])
    rc = demo.run(str(ws))
    out = capsys.readouterr().out
    assert rc == 0
    assert str(ws) in out  # points serve/mcp at the given workspace
    assert "safe to delete" not in out  # did not scaffold a throwaway
