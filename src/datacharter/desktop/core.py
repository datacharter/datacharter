"""Desktop-app plumbing: config/recents, port pick, and the server thread.

Kept free of pywebview so it is unit-testable everywhere; the GUI glue lives in
`datacharter.desktop.__init__` and imports the webview library lazily.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
from pathlib import Path

import httpx

__all__ = [
    "CONFIG_PATH", "load_config", "save_config", "remember", "find_free_port", "ServerHandle",
]

CONFIG_PATH = Path.home() / ".datacharter-desktop.json"
_MAX_RECENTS = 8


def load_config(path: Path = CONFIG_PATH) -> dict:
    try:
        cfg = json.loads(path.read_text())
        if isinstance(cfg, dict):
            return cfg
    except (OSError, ValueError):
        pass
    return {"last": None, "recents": []}


def save_config(cfg: dict, path: Path = CONFIG_PATH) -> None:
    # A broken config store must not break the app.
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(cfg, indent=2))


def remember(workspace: Path | str, path: Path = CONFIG_PATH) -> dict:
    """Set the last workspace and push it onto the deduped, capped recents list."""
    ws = str(Path(workspace).resolve())
    cfg = load_config(path)
    recents = [ws] + [r for r in cfg.get("recents", []) if r != ws]
    cfg.update(last=ws, recents=recents[:_MAX_RECENTS])
    save_config(cfg, path)
    return cfg


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerHandle:
    """Runs the DataCharter server for one workspace on a background thread."""

    def __init__(self) -> None:
        self._server = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None
        self.workspace: Path | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, workspace: Path | str) -> int:
        import uvicorn

        from datacharter.server import create_app

        self.workspace = Path(workspace)
        self.port = find_free_port()
        app = create_app(self.workspace, host="127.0.0.1", port=self.port)
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._server.install_signal_handlers = lambda: None  # GUI owns signals
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        return self.port

    def wait_ready(self, timeout_s: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"{self.url}/api/health", timeout=2.0)
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        return False

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)

    def restart(self, workspace: Path | str) -> int:
        self.stop()
        self.__init__()  # fresh state
        return self.start(workspace)
