"""The ONE way to build a governed ToolBox.

ToolBox used to be hand-assembled at every entry point (serve, `datacharter
mcp`, `eval`, the compare-guides arm) with different kwargs — and every path
that wasn't `serve` silently shipped with weaker governance (no auto-detected
PII, no snapshot overrides). A missing kwarg is invisible; a missing parameter
here is a TypeError. Every entry path MUST go through this module.
"""

from __future__ import annotations

import sys
from typing import Any

from datacharter.agent.tools import ToolBox

__all__ = ["build_toolbox", "detect_auto_pii"]


async def detect_auto_pii(engine) -> set[str]:
    """Value-based PII detection, normalized to the lowercase column-name set
    ToolBox consumes. Detection failure is surfaced on stderr — a silent empty
    set here means silently unmasked columns downstream."""
    from datacharter.contracts.pii import detect_pii

    try:
        detected = await detect_pii(engine)
    except Exception as exc:  # noqa: BLE001 — degrade loudly, never crash serving
        print(f"warning: PII auto-detection failed ({exc}); "
              "only contract-declared PII will be masked.", file=sys.stderr)
        return set()
    return {c.lower() for cols in detected.values() for c in cols}


def build_toolbox(
    engine: Any,
    charter: Any,
    *,
    auto_pii: set[str],
    recorder: Any = None,
    canary: Any = None,
    guides_override: str | None = None,
) -> ToolBox:
    """Every governance input is explicit and non-defaultable where it matters:
    `auto_pii` has no default so no call site can forget detection, and
    `local_access`/`policies`/`guides` always come from the charter itself.
    `guides_override` exists solely for the eval compare-guides arm."""
    return ToolBox(
        engine,
        charter.sources,
        auto_pii=auto_pii,
        local_access=charter.local_access,
        guides=charter.guides if guides_override is None else guides_override,
        recorder=recorder,
        canary=canary,
        policies=charter.policies,
        metrics=charter.metrics,
        quarantine=charter.quarantine_enabled,
    )
