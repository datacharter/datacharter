"""Which backend powers the chat agent: the OpenAI-wire LLM, or local Claude Code."""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_FILE = ".datacharter/agent.json"
#: "none" = explicitly disconnected: the chat shows the connect choices again.
_VALID = ("llm", "claude-code", "none")


def get_backend(workspace: Path) -> str:
    path = workspace / _CONFIG_FILE
    if not path.exists():
        return "llm"
    try:
        backend = json.loads(path.read_text()).get("backend", "llm")
    except Exception:
        return "llm"
    return backend if backend in _VALID else "llm"


def set_backend(workspace: Path, backend: str) -> None:
    if backend not in _VALID:
        raise ValueError(f"unknown backend: {backend!r}")
    path = workspace / _CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"backend": backend}))
