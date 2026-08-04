"""Every artifact must agree on the version — server.json was forgotten once
(the MCP Registry rejects duplicate versions), and the desktop Info.plist
shipped 0.0.0 for months. What can drift, gets a test."""

import json
from pathlib import Path

from datacharter import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_server_json_matches_package_version():
    data = json.loads((ROOT / "server.json").read_text())
    assert data["version"] == __version__
    for pkg in data.get("packages", []):
        assert pkg["version"] == __version__


def test_desktop_spec_reads_the_real_version():
    # The spec parses __init__.py for Info.plist; the line it greps must exist
    # in the exact shape it expects.
    spec = (ROOT / "desktop" / "datacharter.spec").read_text()
    assert "CFBundleShortVersionString" in spec
    init = (ROOT / "src" / "datacharter" / "__init__.py").read_text()
    line = next(ln for ln in init.splitlines() if ln.startswith("__version__"))
    assert line.split('"')[1] == __version__
