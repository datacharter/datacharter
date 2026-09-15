"""HTTP OCI image: build-from-source, non-root, MCP HTTP on 8765."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "packaging" / "oci" / "Dockerfile"


def test_http_image_is_mcp_http_nonroot():
    text = DOCKERFILE.read_text()
    assert "python:3.12-slim" in text
    assert "10001" in text
    assert "USER" in text
    assert "EXPOSE 8765" in text
    assert "mcp" in text
    assert "--http" in text
    assert "0.0.0.0" in text
    assert "pip install" in text
    assert "datacharter==" not in text


def test_stdio_catalog_dockerfile_still_pins_pypi():
    text = (ROOT / "Dockerfile").read_text()
    assert 'CMD ["datacharter", "mcp", "/workspace"]' in text
    assert "datacharter==" in text
    assert "--http" not in text
