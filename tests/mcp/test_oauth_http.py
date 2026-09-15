"""OAuth on POST /mcp: 401 + RFC 9728 metadata, valid bearer passes."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.mcp.auth import AllowAll
from datacharter.mcp.oauth import OAuthConfig, OAuthVerifier
from datacharter.server import create_app

ISS = "https://auth.example.test"
AUD = "https://datacharter.example.test/mcp"


class _StaticJwks:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):  # noqa: ARG002
        class _Key:
            key = self.public_key

        return _Key()


@pytest.fixture
def oauth_client(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    verifier = OAuthVerifier(
        OAuthConfig(issuer=ISS, audience=AUD, jwks_uri="https://auth.example.test/jwks"),
        jwks_client=_StaticJwks(public),
    )
    app = create_app(tmp_path, mcp_authenticator=verifier)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c, private


def _rpc(method="ping", id_=1, **params):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params:
        msg["params"] = params
    return msg


def _bearer(private, **claims):
    now = int(time.time())
    payload = {"iss": ISS, "aud": AUD, "sub": "agent-1", "iat": now, "exp": now + 3600, **claims}
    return "Bearer " + jwt.encode(payload, private, algorithm="RS256")


def test_no_token_is_401_with_resource_metadata(oauth_client):
    client, _ = oauth_client
    resp = client.post("/mcp", json=_rpc())
    assert resp.status_code == 401
    www = resp.headers.get("www-authenticate", "")
    assert www.startswith("Bearer ")
    assert "resource_metadata=" in www
    assert "/.well-known/oauth-protected-resource" in www


def test_valid_token_allows_tools_list(oauth_client):
    client, private = oauth_client
    resp = client.post(
        "/mcp",
        json=_rpc("tools/list"),
        headers={"authorization": _bearer(private)},
    )
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "query" in names


def test_well_known_metadata_when_oauth_on(oauth_client):
    client, _ = oauth_client
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"] == AUD
    assert body["authorization_servers"] == [ISS]
    assert body["bearer_methods_supported"] == ["header"]


def test_well_known_is_404_when_auth_is_off(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path, mcp_authenticator=AllowAll())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/.well-known/oauth-protected-resource").status_code == 404


def test_oauth_allows_non_loopback_host(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OAuthVerifier(
        OAuthConfig(issuer=ISS, audience=AUD, jwks_uri="https://auth.example.test/jwks"),
        jwks_client=_StaticJwks(private.public_key()),
    )
    app = create_app(tmp_path, host="0.0.0.0", mcp_authenticator=verifier)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        resp = client.post(
            "/mcp",
            json=_rpc(),
            headers={"authorization": _bearer(private), "host": "10.1.2.3:8321"},
        )
        assert resp.status_code == 200
