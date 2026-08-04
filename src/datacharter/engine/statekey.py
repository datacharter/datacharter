"""Resolve the local state-DB encryption key (DESIGN D8).

Shared by `serve` and the CLI commands so every process opens the same
`.datacharter/state.duckdb` — env var first, then the OS keyring, generating and
storing a key on first use. Returns None when neither is available (headless
without a keyring backend); the engine then runs the state DB unencrypted.
"""

from __future__ import annotations

import os

__all__ = ["resolve_state_key"]


def resolve_state_key() -> str | None:
    env = os.environ.get("DATACHARTER_STATE_KEY")
    if env:
        return env
    try:
        import keyring  # noqa: PLC0415

        key = keyring.get_password("datacharter", "state_encryption_key")
        if not key:
            import secrets  # noqa: PLC0415

            key = secrets.token_urlsafe(32)
            keyring.set_password("datacharter", "state_encryption_key", key)
        return key
    except Exception as exc:
        import sys

        # Falling back to an UNENCRYPTED state DB must never be silent — the
        # user's snapshots may hold real data they believe is encrypted at rest.
        print(
            f"warning: no OS keyring available ({exc}) — the local state DB "
            f"(snapshots, history) will be UNENCRYPTED. Set DATACHARTER_STATE_KEY "
            f"to encrypt it.",
            file=sys.stderr,
        )
        return None
