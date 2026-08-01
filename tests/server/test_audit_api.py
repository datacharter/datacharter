"""Surface wiring: chat writes attributed audit entries; audit toggle honored."""

import pytest
from fastapi.testclient import TestClient

from datacharter.audit.evidence import read_entries, verify_chain
from datacharter.cli import main as cli_main
from datacharter.server import create_app


class FakeLLM:
    model = "fake-model"
    base_url = "http://fake"
    api_key = "x"

    async def stream(self, messages, tools):
        from datacharter.agent.llm import Delta

        for d in [Delta(text="There are 90 orders.")]:
            yield d


def _app(tmp_path, llm=None):
    cli_main(["init", str(tmp_path), "--demo"])
    return create_app(tmp_path, llm=llm)


def test_chat_ask_writes_session_and_verifies(tmp_path):
    with TestClient(_app(tmp_path, llm=FakeLLM()), base_url="http://127.0.0.1") as c:
        r = c.post("/api/agent/ask", json={"question": "how many orders?"})
        assert r.status_code == 200
    entries = read_entries(tmp_path)
    sessions = [e for e in entries if e["type"] == "session"]
    assert len(sessions) == 1
    s = sessions[0]
    assert s["surface"] == "chat"
    assert s["model"] == "fake-model"
    assert s["question"] == "how many orders?"
    ok, _, _ = verify_chain(tmp_path)
    assert ok


def test_audit_off_writes_nothing(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = (tmp_path / "charter.yaml").read_text()
    (tmp_path / "charter.yaml").write_text(charter + "\naudit: off\n")
    with TestClient(create_app(tmp_path, llm=FakeLLM()), base_url="http://127.0.0.1") as c:
        c.post("/api/agent/ask", json={"question": "hi"})
    assert read_entries(tmp_path) == []


def test_audit_toggle_bad_value_rejected(tmp_path):
    from datacharter.contracts import load_charter
    from datacharter.contracts.loader import CharterError

    cli_main(["init", str(tmp_path)])
    charter = (tmp_path / "charter.yaml").read_text()
    (tmp_path / "charter.yaml").write_text(charter + "\naudit: maybe\n")
    with pytest.raises(CharterError, match="audit"):
        load_charter(tmp_path)
