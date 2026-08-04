"""Desktop plumbing: config/recents, server thread, and the smoke path."""

from pathlib import Path

import pytest

from datacharter.cli import main as cli_main
from datacharter.desktop import main as desktop_main
from datacharter.desktop.core import ServerHandle, load_config, remember, save_config


@pytest.fixture
def ui_bundle():
    """The battery's ui-served check needs a UI bundle; CI checkouts have none
    (it's gitignored — real bundles are verified in the wheel/frozen gates)."""
    import datacharter.server as srv

    static = Path(srv.__file__).parent / "static"
    index = static / "index.html"
    created = not index.exists()
    if created:
        static.mkdir(exist_ok=True)
        index.write_text('<!doctype html><div id="root"></div>')
    yield
    if created:
        index.unlink(missing_ok=True)


def test_config_roundtrip(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    assert load_config(cfg_path) == {"last": None, "recents": []}
    save_config({"last": "/a", "recents": ["/a"]}, cfg_path)
    assert load_config(cfg_path)["last"] == "/a"


def test_remember_dedupes_and_caps(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    for i in range(10):
        remember(tmp_path / f"ws{i}", cfg_path)
    remember(tmp_path / "ws9", cfg_path)  # dup of most recent
    cfg = load_config(cfg_path)
    assert cfg["last"].endswith("ws9")
    assert len(cfg["recents"]) == 8  # capped
    assert len(set(cfg["recents"])) == 8  # deduped


def test_server_handle_serves_and_stops(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    h = ServerHandle()
    h.start(tmp_path)
    try:
        assert h.wait_ready(timeout_s=30)
        import httpx

        assert httpx.get(f"{h.url}/api/health", timeout=5).status_code == 200
    finally:
        h.stop()


def test_smoke_with_workspace(tmp_path, capsys, ui_bundle):
    cli_main(["init", str(tmp_path), "--demo"])
    assert desktop_main(["--smoke", "--workspace", str(tmp_path)]) == 0
    assert "smoke OK" in capsys.readouterr().err


def test_smoke_falls_back_to_demo(capsys, ui_bundle):
    assert desktop_main(["--smoke", "--demo"]) == 0
    assert "smoke OK" in capsys.readouterr().err


def test_preferred_port_is_stable_across_calls(tmp_path):
    from datacharter.desktop.core import preferred_port

    cfg = tmp_path / "cfg.json"
    first = preferred_port(cfg)
    assert preferred_port(cfg) == first  # same origin -> localStorage survives


def test_preferred_port_falls_back_when_taken(tmp_path):
    import socket

    from datacharter.desktop.core import load_config, preferred_port

    cfg = tmp_path / "cfg.json"
    first = preferred_port(cfg)
    with socket.socket() as s:
        s.bind(("127.0.0.1", first))
        s.listen(1)
        second = preferred_port(cfg)
    assert second != first
    assert load_config(cfg)["port"] == second  # remembers the replacement
