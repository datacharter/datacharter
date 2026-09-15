"""OAuth 2.1 resource-server: RS256 bearer JWT, off unless env is set."""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from starlette.requests import Request

from datacharter.mcp.auth import AllowAll, Authenticator, AuthError, Principal

__all__ = ["OAuthConfig", "OAuthVerifier", "authenticator_from_env"]

_ENV_ISS = "DATACHARTER_OAUTH_ISSUER"
_ENV_AUD = "DATACHARTER_OAUTH_AUDIENCE"
_ENV_JWKS = "DATACHARTER_OAUTH_JWKS_URI"


@dataclass(frozen=True)
class OAuthConfig:
    issuer: str
    audience: str
    jwks_uri: str


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError(401, "missing_token")
    return token.strip()


class OAuthVerifier:
    """Validate Authorization: Bearer JWT (RS256, iss, aud, exp)."""

    def __init__(self, config: OAuthConfig, *, jwks_client=None) -> None:
        self.config = config
        self._jwks = jwks_client or jwt.PyJWKClient(config.jwks_uri)

    async def authenticate(self, request: Request) -> Principal:
        token = _bearer_token(request)
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.config.audience,
                issuer=self.config.issuer,
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError(401, "invalid_token") from exc
        return Principal(subject=claims.get("sub"), claims=claims)


def authenticator_from_env() -> Authenticator:
    """OAuthVerifier when issuer, audience, and jwks_uri are all set; else AllowAll."""
    issuer = (os.environ.get(_ENV_ISS) or "").strip()
    audience = (os.environ.get(_ENV_AUD) or "").strip()
    jwks_uri = (os.environ.get(_ENV_JWKS) or "").strip()
    if issuer and audience and jwks_uri:
        return OAuthVerifier(OAuthConfig(issuer=issuer, audience=audience, jwks_uri=jwks_uri))
    return AllowAll()
