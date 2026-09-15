"""LLMClient env resolution: SpaceXAI keys stay on api.x.ai."""

from datacharter.agent.llm import LLMClient


def test_xai_key_used_when_base_is_xai(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DATACHARTER_MODEL", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    cli = LLMClient(base_url="https://api.x.ai/v1")
    assert cli.api_key == "xai-secret"
    assert cli.model == "grok-4.6"


def test_xai_key_ignored_on_other_bases(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    cli = LLMClient(base_url="https://api.openai.com/v1")
    assert cli.api_key == ""


def test_openai_key_wins_on_xai_base(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    cli = LLMClient(base_url="https://api.x.ai/v1")
    assert cli.api_key == "openai-key"


def test_explicit_model_wins_on_xai_base(monkeypatch) -> None:
    monkeypatch.delenv("DATACHARTER_MODEL", raising=False)
    cli = LLMClient(base_url="https://api.x.ai/v1", model="grok-4.5")
    assert cli.model == "grok-4.5"
