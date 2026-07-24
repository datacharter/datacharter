"""End-to-end: build the wheel, install it clean, serve, hit the API. Marked slow."""

import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_serves_ui_and_api(tmp_path):
    if not (ROOT / "src" / "datacharter" / "server" / "static" / "index.html").exists():
        pytest.skip("UI not built (run scripts/build_ui.sh)")

    subprocess.run(["uv", "build", "--wheel", "-o", str(tmp_path / "dist")], cwd=ROOT, check=True)
    wheel = next((tmp_path / "dist").glob("*.whl"))

    venv = tmp_path / "venv"
    subprocess.run(["uv", "venv", str(venv)], check=True)
    py = str(venv / "bin" / "python")
    subprocess.run(["uv", "pip", "install", "--python", py, str(wheel)], check=True)

    proc = subprocess.Popen(
        [str(venv / "bin" / "datacharter"), "serve", "--port", "8399"],
        cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                if urlopen("http://127.0.0.1:8399/api/health", timeout=1).status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            pytest.fail("server did not come up")
        assert b"<title>DataCharter</title>" in urlopen("http://127.0.0.1:8399/", timeout=2).read()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
