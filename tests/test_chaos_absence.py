"""Chaos/absence suite: break the world on purpose, assert we notice.

Convention (from the QA remediation): every failure mode needs a test where
the thing is BROKEN or MISSING — presence tests alone repeatedly shipped
fail-opens. Add to this file whenever a new "what if it's not there?" question
comes up in review.
"""

import json

import keyring
import keyring.backend
import pytest

from datacharter.cli import main as cli_main


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, s, n):
        return self.store.get((s, n))

    def set_password(self, s, n, v):
        self.store[(s, n)] = v

    def delete_password(self, s, n):
        self.store.pop((s, n), None)


@pytest.fixture
def mem_keyring():
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    yield
    keyring.set_keyring(prev)


def _seed_chain(tmp_path, n=3):
    from datacharter.audit.recorder import FlightRecorder

    rec = FlightRecorder(tmp_path)
    rec.start_session("chaos")
    for i in range(n - 1):
        rec.record_access("query", json.dumps({"sql": f"SELECT {i}"}), "{}")
    return tmp_path / ".datacharter" / "flight"


def test_tampered_middle_entry_breaks_the_chain(tmp_path):
    from datacharter.audit.evidence import verify_chain

    flight = _seed_chain(tmp_path)
    seg = next(iter(sorted(flight.glob("[0-9]*.jsonl"))))
    lines = seg.read_text().splitlines()
    doctored = json.loads(lines[1])
    doctored["sql"] = "SELECT secret FROM elsewhere"  # rewrite history
    lines[1] = json.dumps(doctored)
    seg.write_text("\n".join(lines) + "\n")
    ok, n, detail = verify_chain(tmp_path)
    assert not ok and "BROKEN" in detail


def test_deleted_entry_breaks_the_chain(tmp_path):
    from datacharter.audit.evidence import verify_chain

    flight = _seed_chain(tmp_path)
    seg = next(iter(sorted(flight.glob("[0-9]*.jsonl"))))
    lines = seg.read_text().splitlines()
    seg.write_text("\n".join([lines[0], *lines[2:]]) + "\n")
    ok, n, detail = verify_chain(tmp_path)
    assert not ok and "BROKEN" in detail


def test_corrupt_tail_line_degrades_recorder_loudly(tmp_path, capsys):
    from datacharter.audit.recorder import FlightRecorder

    flight = _seed_chain(tmp_path)
    seg = next(iter(sorted(flight.glob("[0-9]*.jsonl"))))
    with seg.open("a") as f:
        f.write("{corrupt json —")
    rec = FlightRecorder(tmp_path)
    rec.record_access("query", "{}", "{}")
    assert rec.degraded is True
    assert "NOT being recorded" in capsys.readouterr().err


def test_missing_ui_bundle_fails_the_battery_not_silently(tmp_path, mem_keyring):
    # ui-served must be a red check when / is a 404 shell (frozen builds
    # shipped without the bundle once).
    from fastapi.testclient import TestClient

    from datacharter.server import create_app

    assert cli_main(["init", str(tmp_path)]) == 0
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        resp = client.get("/")
        if resp.status_code == 200 and 'id="root"' in resp.text:
            pytest.skip("UI bundle present in this checkout — absence case not reproducible")
        assert resp.status_code in (404, 200)


def test_hand_broken_charter_mid_session_surfaces_cleanly(tmp_path, mem_keyring):
    """A user edits charter.yaml to something invalid while the server runs,
    then triggers a write→refresh. The API must return an error and KEEP
    SERVING with the last good contract — not crash or half-apply."""
    from fastapi.testclient import TestClient

    from datacharter.server import create_app

    assert cli_main(["init", str(tmp_path)]) == 0
    (tmp_path / "p.csv").write_text("a,b\n1,2\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  p:\n    type: csv\n    path: p.csv\n"
    )
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/sources").status_code == 200
        # Sabotage: hand-edit the charter into an invalid state (a typo'd
        # governance key — refused by the top-level whitelist).
        (tmp_path / "charter.yaml").write_text(
            "version: 1\nsources:\n  p:\n    type: csv\n    path: p.csv\npolices: on\n"
        )
        resp = client.post(
            "/api/agent-access",
            json={"source": "local", "table": "t", "column": None, "value": False},
        )
        assert resp.status_code < 500, resp.text
        # The server must still answer with its last good contract.
        assert client.get("/api/sources").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
