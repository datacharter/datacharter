"""Continuous compliance: run the governance gates in one pass and report.

The individual checks (`test`, `drift`, `access diff`, `redteam`) each already
exit non-zero on a violation. A compliance monitor aggregates them into a single
status a scheduler can alert on — point-in-time `evidence` becomes a repeatable
signal. This module holds only the value types and rendering; the CLI runs the
checks and builds the report, so there is no import cycle with the commands.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

__all__ = ["CheckResult", "ComplianceReport", "render_report"]


@dataclass(frozen=True)
class CheckResult:
    """One gate's outcome. `ok` is the pass/fail; `detail` is its captured output."""

    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False


@dataclass
class ComplianceReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """The monitor passes when no run check failed. A skipped check is not a failure."""
        return all(r.ok for r in self.results if not r.skipped)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [
                {"name": r.name, "ok": r.ok, "skipped": r.skipped, "detail": r.detail.strip()}
                for r in self.results
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def render_report(report: ComplianceReport) -> str:
    """Human-readable status block: one line per check, then an overall verdict."""
    lines = ["Compliance monitor"]
    for r in report.results:
        mark = "–" if r.skipped else ("✓" if r.ok else "✗")
        note = " (skipped)" if r.skipped else ""
        lines.append(f"  {mark} {r.name}{note}")
    lines.append("")
    lines.append("PASS — every gate held." if report.ok else "FAIL — a gate reported a violation.")
    return "\n".join(lines)
