"""Canary tripwires: synthetic honeytokens masked by the same machinery they test.

`local.canaries` holds fake PII whose values embed unique per-workspace tokens.
Agents querying it get `•••` like any masked column — so a token appearing in any
agent-bound result is proof the masking/guard layer failed. Near-zero false
positives by construction: there is no legitimate path for a token to surface.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CanaryGuard", "ensure_canaries", "CANARY_FILE"]

CANARY_FILE = ".datacharter/canary.json"
_N_TOKENS = 3


@dataclass
class CanaryGuard:
    tokens: list[str]
    mode: str  # "block" | "log"

    def scan(self, text: str) -> str | None:
        """First token found in agent-bound text, else None."""
        for t in self.tokens:
            if t in text:
                return t
        return None


def _load_or_create_tokens(workspace: Path) -> list[str]:
    path = workspace / CANARY_FILE
    if path.exists():
        try:
            tokens = json.loads(path.read_text()).get("tokens") or []
            if tokens:
                return tokens
        except (ValueError, OSError):
            pass
    tokens = [f"canary-{secrets.token_hex(6)}" for _ in range(_N_TOKENS)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tokens": tokens}, indent=2))
    return tokens


def ensure_canaries(workspace: Path | str, engine, mode: str | None) -> CanaryGuard | None:
    """Plant (or refresh) local.canaries when enabled; returns the guard or None.

    Planting failures disable the guard rather than break startup.
    """
    if mode is None:
        return None
    workspace = Path(workspace)
    tokens = _load_or_create_tokens(workspace)
    rows = ", ".join(
        f"('{t}@tripwire.invalid', '{t}', '{t}')" for t in tokens
    )
    sql = f"SELECT * FROM (VALUES {rows}) AS t(email, phone, ssn)"
    try:
        engine.snapshot_sync(sql, "canaries")
    except Exception:
        return None
    return CanaryGuard(tokens=tokens, mode=mode)
