"""Import-the-world selftest: catches modules a frozen build silently dropped.

PyInstaller only bundles what it can trace; dynamic imports (duckdb's pytz,
fastapi's python-multipart, the contract writer's ruamel) have each shipped
missing from a green build. This walks every datacharter module plus the
dynamic tripwires and imports them for real — in the artifact, before release.
"""

from __future__ import annotations

import importlib
import pkgutil

__all__ = ["run_selftest"]

#: Dependencies imported lazily somewhere in the codebase — exactly the ones
#: a static trace misses. Extend this list whenever a new lazy import lands.
DYNAMIC_TRIPWIRES = [
    "duckdb",
    "pytz",                # duckdb TIMESTAMPTZ materialization
    "multipart",           # fastapi UploadFile
    "ruamel.yaml",         # contract writer round-trip
    "keyring",             # state-DB encryption key
    "dotenv",              # secret resolution
    "yaml",
    "pydantic",
    "fastapi",
    "uvicorn",
    "httpx",
]

#: Floor for the module walk. A frozen importer that can't enumerate packages
#: returns nothing — which must read as FAILURE, not as "nothing to check".
_MIN_OWN_MODULES = 30


def _own_modules() -> list[str]:
    import datacharter

    names = ["datacharter"]
    for m in pkgutil.walk_packages(datacharter.__path__, prefix="datacharter."):
        names.append(m.name)
    return names


def run_selftest() -> list[tuple[str, bool, str]]:
    """Import every module; returns (name, ok, detail) per failure class."""
    results: list[tuple[str, bool, str]] = []
    own = _own_modules()
    if len(own) < _MIN_OWN_MODULES:
        results.append((
            "module-walk", False,
            f"only {len(own)} datacharter modules enumerable — the frozen "
            f"importer cannot walk packages, so this selftest is blind",
        ))
    failures = []
    for name in own:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — any import failure is the finding
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    results.append((
        f"import-own ({len(own)} modules)", not failures, "; ".join(failures) or "ok",
    ))
    for name in DYNAMIC_TRIPWIRES:
        try:
            importlib.import_module(name)
            results.append((f"tripwire {name}", True, "ok"))
        except Exception as exc:  # noqa: BLE001
            results.append((f"tripwire {name}", False, f"{type(exc).__name__}: {exc}"))
    return results


def format_results(results: list[tuple[str, bool, str]]) -> str:
    lines = [f"  {'✓' if ok else '✗'} {name}: {detail}" for name, ok, detail in results]
    failed = sum(1 for _, ok, _ in results if not ok)
    lines.append(f"selftest: {len(results) - failed}/{len(results)} passed")
    return "\n".join(lines)
