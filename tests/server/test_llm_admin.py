import keyring
import keyring.backend
import pytest

from datacharter.server import llm_admin


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
def env_and_keyring(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    yield
    keyring.set_keyring(prev)


def test_unconfigured_is_none(tmp_path, env_and_keyring):
    assert llm_admin.load_llm(tmp_path) is None
    assert llm_admin.llm_status(None)["available"] is False


def test_save_then_load_round_trip(tmp_path, env_and_keyring):
    form = llm_admin.LLMConfigForm(
        base_url="http://localhost:1234/v1", api_key="sk-secret", model="my-model"
    )
    llm_admin.save_llm(tmp_path, form)

    # key goes to the keyring; base_url/model to a local file — no secret on disk.
    assert keyring.get_password("datacharter", llm_admin.LLM_KEY_NAME) == "sk-secret"
    assert "sk-secret" not in (tmp_path / ".datacharter" / "llm.json").read_text()

    client = llm_admin.load_llm(tmp_path)
    assert client is not None
    assert client.base_url == "http://localhost:1234/v1"
    assert client.model == "my-model"
    status = llm_admin.llm_status(client)
    assert status["available"] and status["has_key"] and status["model"] == "my-model"


def test_cli_local_wins(tmp_path, env_and_keyring):
    from datacharter.agent.llm import LLMClient

    cli = LLMClient(base_url="http://127.0.0.1:11434/v1", api_key="ollama", model="qwen3:8b")
    assert llm_admin.load_llm(tmp_path, cli) is cli


def test_config_endpoint_makes_agent_available(tmp_path, env_and_keyring):
    from fastapi.testclient import TestClient

    from datacharter.cli import main as cli_main
    from datacharter.server import create_app

    cli_main(["init", str(tmp_path), "--demo"])
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/api/agent/available").json()["available"] is False
        r = c.post(
            "/api/agent/config",
            json={"base_url": "http://localhost:1234/v1", "api_key": "sk-x", "model": "m"},
        )
        assert r.status_code == 200
        avail = c.get("/api/agent/available").json()
        assert avail["available"] is True and avail["model"] == "m"
    # secret in keyring, not in the config file
    assert keyring.get_password("datacharter", llm_admin.LLM_KEY_NAME) == "sk-x"
    assert "sk-x" not in (tmp_path / ".datacharter" / "llm.json").read_text()
