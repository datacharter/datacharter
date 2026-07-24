import json

from fastapi.testclient import TestClient

from datacharter.agent.llm import Delta
from datacharter.cli import _print_attestation
from datacharter.cli import main as cli_main
from datacharter.server import create_app


class _FakeLLM:
    base_url = "http://x"
    model = "m"

    async def stream(self, messages, tools):
        yield Delta(text="hi")


def test_offline_forces_no_llm_even_if_passed(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    app = create_app(tmp_path, llm=_FakeLLM(), offline=True)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/api/agent/available").json()["available"] is False


def test_offline_disables_llm_config_endpoint(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    app = create_app(tmp_path, offline=True)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        resp = c.post("/api/agent/config", json={"base_url": "http://x", "api_key": "k"})
        assert resp.status_code == 403
        assert resp.json()["error"]["type"] == "offline"


def test_attestation_is_written_and_printed(tmp_path, capsys):
    _print_attestation(tmp_path, "127.0.0.1", 8321)
    assert "OFFLINE MODE" in capsys.readouterr().out
    record = json.loads((tmp_path / ".datacharter" / "attestation.json").read_text())
    assert record["mode"] == "offline"
    assert record["llm"] == "disabled"
