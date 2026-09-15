"""OAuth 2.1 resource-server verifier: RS256 JWT, no network."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.requests import Request

from datacharter.mcp.auth import AllowAll, AuthError
from datacharter.mcp.oauth import OAuthConfig, OAuthVerifier, authenticator_from_env

ISS = "https://auth.example.test"
AUD = "https://datacharter.example.test/mcp"


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


class _StaticJwks:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):  # noqa: ARG002
        class _Key:
            key = self.public_key

        return _Key()


def _token(private, **claims):
    now = int(time.time())
    payload = {
        "iss": ISS,
        "aud": AUD,
        "sub": "agent-1",
        "iat": now,
        "exp": now + 3600,
        **claims,
    }
    return jwt.encode(payload, private, algorithm="RS256")


def _req(authorization: str | None = None) -> Request:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return Request({"type": "http", "headers": headers})


def _verifier(public):
    cfg = OAuthConfig(issuer=ISS, audience=AUD, jwks_uri="https://auth.example.test/jwks")
    return OAuthVerifier(cfg, jwks_client=_StaticJwks(public))


async def test_valid_token_returns_subject(keys):
    private, public = keys
    principal = await _verifier(public).authenticate(_req("Bearer " + _token(private)))
    assert principal.subject == "agent-1"
    assert principal.claims["iss"] == ISS


@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer", "Bearer "],
)
async def test_missing_or_non_bearer_is_401(keys, header):
    _, public = keys
    with pytest.raises(AuthError) as exc:
        await _verifier(public).authenticate(_req(header))
    assert exc.value.status == 401
    assert exc.value.detail == "missing_token"


async def test_expired_wrong_aud_wrong_iss_malformed(keys):
    private, public = keys
    v = _verifier(public)
    expired = _token(private, exp=int(time.time()) - 10)
    with pytest.raises(AuthError) as exc:
        await v.authenticate(_req("Bearer " + expired))
    assert exc.value.detail == "invalid_token"
    with pytest.raises(AuthError):
        await v.authenticate(_req("Bearer " + _token(private, aud="https://other")))
    with pytest.raises(AuthError):
        await v.authenticate(_req("Bearer " + _token(private, iss="https://evil.test")))
    with pytest.raises(AuthError):
        await v.authenticate(_req("Bearer not-a-jwt"))


def test_authenticator_from_env_defaults_to_allow_all(monkeypatch):
    for name in (
        "DATACHARTER_OAUTH_ISSUER",
        "DATACHARTER_OAUTH_AUDIENCE",
        "DATACHARTER_OAUTH_JWKS_URI",
    ):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(authenticator_from_env(), AllowAll)


def test_mcp_bind_allowed_requires_oauth_off_loopback(keys):
    from datacharter.mcp.http import mcp_bind_allowed

    _, public = keys
    assert mcp_bind_allowed("127.0.0.1", AllowAll()) is True
    assert mcp_bind_allowed("0.0.0.0", AllowAll()) is False
    assert mcp_bind_allowed("0.0.0.0", _verifier(public)) is True


def test_authenticator_from_env_requires_all_three(monkeypatch):
    monkeypatch.setenv("DATACHARTER_OAUTH_ISSUER", ISS)
    monkeypatch.setenv("DATACHARTER_OAUTH_AUDIENCE", AUD)
    monkeypatch.delenv("DATACHARTER_OAUTH_JWKS_URI", raising=False)
    assert isinstance(authenticator_from_env(), AllowAll)
    monkeypatch.setenv("DATACHARTER_OAUTH_JWKS_URI", "https://auth.example.test/jwks")
    auth = authenticator_from_env()
    assert isinstance(auth, OAuthVerifier)
    assert auth.config.issuer == ISS
