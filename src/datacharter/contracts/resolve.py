"""`${NAME}` secret/variable resolution: process env → .env → OS keyring (D7)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import dotenv_values

__all__ = ["SecretResolver", "UnresolvedReference", "FULL_REF", "INLINE_REF"]

KEYRING_SERVICE = "datacharter"

FULL_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
INLINE_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class UnresolvedReference(Exception):
    """A ${NAME} reference could not be resolved from any store."""

    def __init__(self, name: str, tried: list[str]) -> None:
        self.name = name
        super().__init__(
            f"Could not resolve ${{{name}}}. Tried: {', '.join(tried)}. "
            f"Set the environment variable, add it to .env, or run "
            f"`datacharter secrets set {name}`."
        )


class SecretResolver:
    """Resolves ${NAME} references against env, workspace .env, then OS keyring."""

    def __init__(self, workspace: Path, *, lenient: bool = False) -> None:
        env_file = workspace / ".env"
        self._dotenv: dict[str, str] = {
            k: v for k, v in dotenv_values(env_file).items() if v is not None
        }
        # Lenient mode keeps unresolved ${NAME} refs as-is instead of raising —
        # used by `access diff`, which reviews the governance surface (never the
        # secret values) so CI can run it without any credentials configured.
        self._lenient = lenient

    def resolve(self, name: str) -> str:
        value = os.environ.get(name)
        if value is not None:
            return value
        if name in self._dotenv:
            return self._dotenv[name]
        value = self._keyring_get(name)
        if value is not None:
            return value
        if self._lenient:
            return f"${{{name}}}"
        tried = ["environment", ".env", self._keyring_status()]
        raise UnresolvedReference(name, tried)

    def resolve_optional(self, name: str) -> str | None:
        """Resolve ${name}, or None if unset (no raise)."""
        try:
            return self.resolve(name)
        except UnresolvedReference:
            return None

    def interpolate(self, text: str) -> str:
        """Substitute all inline ${NAME} references within a string."""
        return INLINE_REF.sub(lambda m: self.resolve(m.group(1)), text)

    @staticmethod
    def _keyring_get(name: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(KEYRING_SERVICE, name)
        except Exception:
            # No usable backend (headless) — env/.env remain the supported paths.
            return None

    @staticmethod
    def _keyring_status() -> str:
        try:
            import keyring

            keyring.get_keyring()
            return "OS keyring"
        except Exception:
            return "OS keyring (no backend available)"
