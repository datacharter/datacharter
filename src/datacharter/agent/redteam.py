"""The Gauntlet — DataCharter attacks its own governance and reports a score.

Every attack runs through the real `ToolBox.run`, so a green Gauntlet is evidence
about the *actual* governed path (masking + read-only guard + policy guard +
canary scan all fire in one call), not a mock. The oracle reuses the canary
honeytokens as ground-truth secrets: a known sentinel appearing in any result is
proof masking failed — deterministic, and needing zero knowledge of real data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from datacharter.agent.tools import MASKED, ToolBox
from datacharter.audit.canary import CanaryGuard

__all__ = [
    "Attack",
    "GauntletReport",
    "run_gauntlet",
    "ATTACKS",
    "CORPUS_ID",
    "load_corpus",
    "corpus_sha256",
    "corpus_cite",
]

CORPUS_ID = "govbench-v1"
_CORPUS_PATH = Path(__file__).with_name("govbench_v1.json")


@dataclass(frozen=True)
class Attack:
    category: str
    sql: str
    expect: str  # "refuse" (guard must error) | "mask" (values must be masked)
    note: str  # remediation shown on a breach
    needs_policy: bool = False  # only meaningful when a policy is active
    id: str = ""


def load_corpus(path: Path | None = None) -> list[Attack]:
    """Load the frozen GovBench attack list. Edit the JSON and bump CORPUS_ID."""
    data = json.loads((path or _CORPUS_PATH).read_text())
    out: list[Attack] = []
    for row in data["attacks"]:
        out.append(
            Attack(
                category=row["category"],
                sql=row["sql"],
                expect=row["expect"],
                note=row["note"],
                needs_policy=bool(row.get("needs_policy", False)),
                id=str(row.get("id", "")),
            )
        )
    return out


def corpus_sha256(path: Path | None = None) -> str:
    """Canonical SHA-256 of the corpus JSON (sorted keys, compact)."""
    data = json.loads((path or _CORPUS_PATH).read_text())
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def corpus_cite() -> dict:
    return {"id": CORPUS_ID, "sha256": corpus_sha256(), "attacks": len(ATTACKS)}


# Frozen offline battery. PII/honeytoken attacks target local.canaries so the
# oracle has known sentinels; read-only attacks probe every side-effect path.
ATTACKS: list[Attack] = load_corpus()


@dataclass
class GauntletReport:
    #: category -> (withstood, total)
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    not_applicable: int = 0

    @property
    def withstood(self) -> int:
        return sum(w for w, _ in self.by_category.values())

    @property
    def total(self) -> int:
        return sum(t for _, t in self.by_category.values())

    @property
    def ok(self) -> bool:
        return not self.findings


def _judge(attack: Attack, out: str, canary: CanaryGuard) -> str | None:
    """Return a finding string if the attack breached governance, else None."""
    token = canary.scan(out)
    if token is not None:  # a known secret escaped — definitive breach, any category
        return f"[{attack.category}] `{attack.sql}` leaked a honeytoken → {attack.note}"
    if attack.expect == "refuse":
        if not out.startswith("Error:"):
            return f"[{attack.category}] `{attack.sql}` was NOT refused → {attack.note}"
        return None
    # expect == "mask": a refusal is also safe; otherwise the masked marker must
    # be present (no token already guaranteed above). Empty results leak nothing.
    if out.startswith("Error:") or _is_masked(out) or _no_rows(out):
        return None
    return f"[{attack.category}] `{attack.sql}` returned an unmasked value → {attack.note}"


def _is_masked(out: str) -> bool:
    # The result is JSON; json.dumps escapes the • marker to • by default,
    # so check for both the raw and the escaped spelling.
    return MASKED in out or "\\u2022" in out


def _no_rows(out: str) -> bool:
    return '"rows": []' in out or '"rows":[]' in out


async def run_gauntlet(
    toolbox: ToolBox, canary: CanaryGuard, *, policies_active: bool
) -> GauntletReport:
    """Fire every applicable attack through the real ToolBox and score the result."""
    report = GauntletReport()
    # Without planted honeytokens, mask/exfil attacks query a missing table and
    # error out — which the oracle would count as "withstood", a false pass. The
    # bait is the whole proof, so its absence is itself a breach.
    if not getattr(canary, "planted", True):
        report.findings.append(
            "[setup] honeytokens were NOT planted (local.canaries missing) — "
            "masking was never actually exercised; the verdict proves nothing."
        )
    for attack in ATTACKS:
        if attack.needs_policy and not policies_active:
            report.not_applicable += 1
            continue
        out = await toolbox.run("query", json.dumps({"sql": attack.sql}))
        finding = _judge(attack, out, canary)
        w, t = report.by_category.get(attack.category, (0, 0))
        report.by_category[attack.category] = (w + (0 if finding else 1), t + 1)
        if finding:
            report.findings.append(finding)
    return report


def render_report(report: GauntletReport) -> str:
    """The report card — categories, per-attack breaches, and the verdict."""
    lines = [f"The Gauntlet — {report.total} attacks against this charter's governance", ""]
    for cat, (w, t) in report.by_category.items():
        mark = "✓" if w == t else "✗"
        lines.append(f"  {mark} {cat:<22} {w}/{t} withstood")
    for finding in report.findings:
        lines.append(f"    ✗ {finding}")
    if report.not_applicable:
        lines.append(f"  ({report.not_applicable} policy attack(s) not applicable — "
                     f"no policy active on this charter)")
    lines.append("")
    if report.ok:
        lines.append(f"  Score: {report.withstood}/{report.total} attacks withstood. "
                     f"Governance holds. ✅")
    else:
        lines.append(f"  Score: {report.withstood}/{report.total}. "
                     f"{len(report.findings)} BREACH — see above. ❌")
    return "\n".join(lines)
