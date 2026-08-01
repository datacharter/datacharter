"""DataCharter as a desktop app: a native window over the local server.

`datacharter-desktop` (requires the `[desktop]` extra) opens the governed
explorer in an OS webview. `--smoke` starts the server headless and checks
health — the CI verification path for platforms we can't drive a GUI on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from datacharter.desktop.core import ServerHandle, load_config, remember

__all__ = ["main"]


def _resolve_initial(args) -> Path | None:
    """Workspace to boot with, or None to ask via the picker at GUI start."""
    if args.workspace:
        return Path(args.workspace).resolve()
    if args.demo:
        return _demo_workspace()
    last = load_config().get("last")
    if last and (Path(last) / "charter.yaml").exists():
        return Path(last)
    return None


def _demo_workspace() -> Path:
    import tempfile

    from datacharter.cli import DEMO_CHARTER
    from datacharter.demo import write_demo_data

    ws = Path(tempfile.mkdtemp(prefix="datacharter-desktop-demo-"))
    (ws / "charter.yaml").write_text(DEMO_CHARTER)
    write_demo_data(ws)
    return ws


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="datacharter-desktop", description="DataCharter desktop app"
    )
    parser.add_argument("--workspace", help="Workspace folder to open")
    parser.add_argument("--demo", action="store_true", help="Open the bundled demo")
    parser.add_argument(
        "--smoke", action="store_true",
        help="Start the server headless, check health, exit (CI verification)",
    )
    args = parser.parse_args(argv)

    handle = ServerHandle()

    if args.smoke:
        ws = _resolve_initial(args) or _demo_workspace()
        handle.start(ws)
        ok = handle.wait_ready()
        handle.stop()
        print("smoke OK" if ok else "smoke FAILED", file=sys.stderr)
        return 0 if ok else 1

    try:
        import webview
    except ImportError:
        print(
            "pywebview is not installed. Run: pip install 'datacharter[desktop]'",
            file=sys.stderr,
        )
        return 1

    initial = _resolve_initial(args)
    booted = initial or _demo_workspace()
    handle.start(booted)
    if not handle.wait_ready():
        print("DataCharter server failed to start.", file=sys.stderr)
        return 1
    if initial is not None:
        remember(booted)

    window = webview.create_window(
        "DataCharter", handle.url, width=1280, height=850, min_size=(900, 600)
    )

    folder_dialog = getattr(webview, "FOLDER_DIALOG", None)
    if folder_dialog is None:  # pywebview >= 6 renamed the constants
        folder_dialog = webview.FileDialog.FOLDER

    def open_workspace(_menu_item=None) -> None:
        picked = window.create_file_dialog(folder_dialog)
        if not picked:
            return
        ws = Path(picked[0] if isinstance(picked, (list, tuple)) else picked)
        if not (ws / "charter.yaml").exists():
            window.load_html(
                "<h3 style='font-family:sans-serif'>No charter.yaml in that folder.</h3>"
                "<p style='font-family:sans-serif'>Run <code>datacharter init</code> "
                "there first, or pick another workspace.</p>"
            )
            return
        handle.restart(ws)
        if handle.wait_ready():
            remember(ws)
            window.load_url(handle.url)

    def _open_recent(path: str):
        def go(_item=None) -> None:
            if (Path(path) / "charter.yaml").exists():
                handle.restart(path)
                if handle.wait_ready():
                    remember(path)
                    window.load_url(handle.url)

        return go

    def on_start() -> None:
        if initial is None:
            open_workspace()

    try:
        from webview.menu import Menu, MenuAction

        recents = [
            MenuAction(p, _open_recent(p))
            for p in load_config().get("recents", [])
            if (Path(p) / "charter.yaml").exists()
        ]
        menu = [
            Menu(
                "Workspace",
                [MenuAction("Open Workspace…", open_workspace)]
                + ([Menu("Recents", recents)] if recents else []),
            )
        ]
        webview.start(on_start, menu=menu)
    except Exception:
        webview.start(on_start)  # menus are best-effort; the app must still open
    finally:
        handle.stop()
    return 0
