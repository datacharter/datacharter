"""Kubelet probes: unauthenticated, host/origin exempt, ready when toolbox exists."""

from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.mcp.auth import AllowAll
from datacharter.mcp.http import create_mcp_http_app
from datacharter.mcp.oauth import OAuthConfig, OAuthVerifier
from datacharter.server import create_app


def test_health_and_ready_on_serve(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.get("/ready").status_code == 200
        assert c.get("/ready").json()["status"] == "ready"


def test_health_and_ready_on_mcp_http(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_mcp_http_app(tmp_path, authenticator=AllowAll())
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.get("/ready").json()["status"] == "ready"


def test_probes_skip_host_and_origin_guards(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path, host="127.0.0.1")
    with TestClient(app, base_url="http://10.1.2.3") as c:
        headers = {"origin": "http://evil.example.test"}
        assert c.get("/health", headers=headers).status_code == 200
        assert c.get("/ready", headers=headers).status_code == 200


def test_probes_need_no_oauth_token(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0

    class _Jwks:
        def get_signing_key_from_jwt(self, token):  # noqa: ARG002
            raise AssertionError("probes must not verify a token")

    verifier = OAuthVerifier(
        OAuthConfig(
            issuer="https://auth.example.test",
            audience="https://datacharter.example.test/mcp",
            jwks_uri="https://auth.example.test/jwks",
        ),
        jwks_client=_Jwks(),
    )
    app = create_mcp_http_app(tmp_path, authenticator=verifier)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/health").status_code == 200
        assert c.get("/ready").status_code == 200


def test_ready_503_without_toolbox():
    from fastapi import FastAPI

    from datacharter.server.probes import attach_probes

    app = FastAPI()
    attach_probes(app)
    with TestClient(app) as c:
        assert c.get("/ready").status_code == 503
        assert c.get("/health").json() == {"status": "ok"}
