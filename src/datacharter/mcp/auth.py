"""Auth seam for MCP over HTTP. AllowAll now; OAuth swaps in later."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.requests import Request

__all__ = ["Principal", "AuthError", "Authenticator", "AllowAll"]


@dataclass(frozen=True)
class Principal:
    """Caller identity. Empty until OAuth is enabled."""

    subject: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)


class AuthError(Exception):
    def __init__(self, status: int = 401, detail: str = "unauthorized") -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


class Authenticator(Protocol):
    async def authenticate(self, request: Request) -> Principal: ...


class AllowAll:
    """Trusted-network default: never rejects, anonymous principal."""

    async def authenticate(self, request: Request) -> Principal:  # noqa: ARG002
        return Principal()
