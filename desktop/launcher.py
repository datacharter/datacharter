"""Frozen-app entrypoint for PyInstaller."""

import multiprocessing
import os
import sys

multiprocessing.freeze_support()

# Windowed (console=False) builds have no stdio; anything that touches
# sys.stdout/err (uvicorn logging, click, tracebacks) must not find None.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")  # noqa: SIM115
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")  # noqa: SIM115

from datacharter.desktop import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
