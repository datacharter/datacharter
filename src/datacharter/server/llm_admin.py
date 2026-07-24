"""Runtime LLM configuration: the API key in the keyring, base_url/model in a file."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from datacharter.agent.llm import LLMClient
from datacharter.contracts import secrets as secretstore
from datacharter.contracts.resolve import KEYRING_SERVICE

__all__ = ["LLMConfigForm", "load_llm", "save_llm", "llm_status", "LLM_KEY_NAME"]

LLM_KEY_NAME = "DATACHARTER_LLM_KEY"
_CONFIG_FILE = ".datacharter/llm.json"


class LLMConfigForm(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


def _config_path(workspace: Path) -> Path:
    return workspace / _CONFIG_FILE


def _read_config(workspace: Path) -> dict:
    path = _config_path(workspace)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _stored_key() -> str | None:
    import keyring  # noqa: PLC0415

    try:
        return keyring.get_password(KEYRING_SERVICE, LLM_KEY_NAME)
    except Exception:
        return None


def save_llm(workspace: Path, form: LLMConfigForm) -> None:
    cfg = _read_config(workspace)
    if form.base_url is not None:
        cfg["base_url"] = form.base_url
    if form.model is not None:
        cfg["model"] = form.model
    path = _config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg))
    if form.api_key:
        secretstore.store_secret(LLM_KEY_NAME, form.api_key)


def load_llm(workspace: Path, cli_llm: LLMClient | None = None) -> LLMClient | None:
    """The active client: an explicit --local wins; else stored config, else env."""
    if cli_llm is not None:
        return cli_llm
    cfg = _read_config(workspace)
    key = _stored_key() or os.environ.get("OPENAI_API_KEY")
    if not (key or cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL")):
        return None
    return LLMClient(base_url=cfg.get("base_url"), api_key=key, model=cfg.get("model"))


def llm_status(client: LLMClient | None) -> dict:
    if client is None:
        return {"available": False, "model": None, "base_url": None, "has_key": False}
    return {
        "available": True,
        "model": getattr(client, "model", None),
        "base_url": getattr(client, "base_url", None),
        "has_key": bool(getattr(client, "api_key", None)),
    }
