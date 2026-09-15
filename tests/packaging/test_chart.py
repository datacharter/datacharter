"""Helm chart: hardened MCP HTTP, OAuth env, kubelet probes. No raw cluster serve."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "chart"


def test_chart_metadata_and_values_exist():
    chart = (CHART / "Chart.yaml").read_text()
    values = (CHART / "values.yaml").read_text()
    assert "name: datacharter" in chart
    assert "apiVersion: v2" in chart
    assert "oauth:" in values
    assert "issuer:" in values
    assert "jwksUri:" in values
    assert "charter:" in values


def test_deployment_is_hardened_mcp_http():
    dep = (CHART / "templates" / "deployment.yaml").read_text()
    values = (CHART / "values.yaml").read_text()
    assert "mcp" in dep
    assert "--http" in dep
    assert "0.0.0.0" in dep
    assert "/health" in dep
    assert "/ready" in dep
    assert ".Values.securityContext" in dep
    assert "runAsNonRoot: true" in values
    assert "runAsUser: 10001" in values
    assert "readOnlyRootFilesystem: true" in values
    assert "allowPrivilegeEscalation: false" in values
    assert "DATACHARTER_OAUTH_ISSUER" in dep
    assert "DATACHARTER_OAUTH_AUDIENCE" in dep
    assert "DATACHARTER_OAUTH_JWKS_URI" in dep
    assert "/tmp" in dep
    assert "emptyDir" in dep


def test_chart_refuses_install_without_oauth():
    helpers = (CHART / "templates" / "_helpers.tpl").read_text()
    combined = helpers + (CHART / "templates" / "deployment.yaml").read_text()
    assert "oauth.issuer" in combined
    assert "fail" in combined


def test_service_exposes_8765():
    svc = (CHART / "templates" / "service.yaml").read_text()
    values = (CHART / "values.yaml").read_text()
    assert ".Values.service.port" in svc
    assert "port: 8765" in values
    assert "ClusterIP" in values


def test_configmap_mounts_charter():
    cm = (CHART / "templates" / "configmap.yaml").read_text()
    assert "charter.yaml" in cm


def test_helm_lint_and_template_require_oauth():
    import shutil
    import subprocess

    if not shutil.which("helm"):
        return
    oauth = [
        "--set",
        "oauth.issuer=https://auth.example.test",
        "--set",
        "oauth.audience=https://datacharter.example.test/mcp",
        "--set",
        "oauth.jwksUri=https://auth.example.test/jwks",
    ]
    lint = subprocess.run(
        ["helm", "lint", str(CHART), *oauth], capture_output=True, text=True
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr
    rendered = subprocess.run(
        ["helm", "template", "dc", str(CHART), *oauth],
        capture_output=True,
        text=True,
        check=True,
    )
    out = rendered.stdout
    assert "runAsNonRoot: true" in out
    assert "path: /health" in out
    assert "DATACHARTER_OAUTH_ISSUER" in out
    missing = subprocess.run(
        ["helm", "template", "dc", str(CHART)],
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0
    assert "oauth.issuer" in missing.stderr
