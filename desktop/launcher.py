"""Frozen-app entrypoint for PyInstaller."""

from datacharter.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
