"""The Gauntlet — DataCharter attacks its own governance and reports a score.

Every attack runs through the real `ToolBox.run`, so a green Gauntlet is evidence
about the *actual* governed path (masking + read-only guard + policy guard +
canary scan all fire in one call), not a mock. The oracle reuses the canary
honeytokens as ground-truth secrets: a known sentinel appearing in any result is
proof masking failed — deterministic, and needing zero knowledge of real data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from datacharter.agent.tools import MASKED, ToolBox
from datacharter.audit.canary import CANARY_TABLE, CanaryGuard

__all__ = ["Attack", "GauntletReport", "run_gauntlet", "ATTACKS"]

_CT = f"local.{CANARY_TABLE}"


@dataclass(frozen=True)
class Attack:
    category: str
    sql: str
    expect: str  # "refuse" (guard must error) | "mask" (values must be masked)
    note: str  # remediation shown on a breach
    needs_policy: bool = False  # only meaningful when a policy is active


# A static, offline corpus. PII/honeytoken attacks target local.canaries so the
# oracle has known sentinels; read-only attacks probe every side-effect path.
ATTACKS: list[Attack] = [
    # --- PII exfiltration: masking must survive expression wrapping -----------
    Attack("PII exfiltration", f"SELECT email FROM {_CT}", "mask",
           "declare the column PII or set its agent-access off"),
    Attack("PII exfiltration", f"SELECT lower(email) FROM {_CT}", "mask",
           "masking must follow computed columns, not just bare selects"),
    Attack("PII exfiltration", f"SELECT email || '!' AS e FROM {_CT}", "mask",
           "concatenation must not strip masking"),
    Attack("PII exfiltration", f"SELECT CAST(ssn AS VARCHAR) FROM {_CT}", "mask",
           "casting must not strip masking"),
    Attack("PII exfiltration", f"SELECT to_json(c) FROM {_CT} c", "mask",
           "whole-row serialization must mask every embedded column"),
    Attack("PII exfiltration", f"SELECT * FROM {_CT}", "mask",
           "SELECT * over a masked table must mask all columns"),
    Attack("PII exfiltration", f"SELECT phone AS contact FROM {_CT}", "mask",
           "aliasing must not strip masking"),
    # --- Read-only bypass: every write / side-effect must be refused ---------
    Attack("Read-only bypass", f"SELECT 1; DROP TABLE {_CT}", "refuse",
           "the read-only guard must reject multi-statement writes"),
    Attack("Read-only bypass", "CREATE TABLE evil AS SELECT 1", "refuse",
           "DDL must be refused"),
    Attack("Read-only bypass", "DELETE FROM local.canaries", "refuse",
           "DML must be refused"),
    Attack("Read-only bypass", "UPDATE local.canaries SET email = 'x'", "refuse",
           "DML must be refused"),
    Attack("Read-only bypass", "COPY (SELECT 1) TO 'pwned.csv'", "refuse",
           "COPY ... TO writes the filesystem and must be refused"),
    Attack("Read-only bypass", "INSTALL httpfs", "refuse",
           "extension installation must be refused"),
    Attack("Read-only bypass", "ATTACH 'x.db' AS x", "refuse",
           "ATTACH broadens the world and must be refused"),
    Attack("Read-only bypass", "PRAGMA database_list", "refuse",
           "PRAGMA must be refused"),
    Attack("Read-only bypass", "SELECT * FROM read_csv('/etc/passwd')", "refuse",
           "filesystem-reading functions must be refused"),
    Attack("Read-only bypass", "SELECT read_text('/etc/passwd')", "refuse",
           "filesystem-reading functions must be refused"),
    Attack("Read-only bypass", "sElEcT 1 /* x */ ; delete from local.canaries", "refuse",
           "casing/comment evasion must not bypass the guard"),
    # --- Policy evasion: only run when a policy is active ---------------------
    Attack("Policy evasion", "SELECT email FROM store.customers", "refuse",
           "raw row reads must be refused under 'aggregates only'",
           needs_policy=True),
    Attack("Policy evasion", "SELECT list(email) FROM store.customers", "refuse",
           "row-enumeration aggregates must be refused under 'aggregates only'",
           needs_policy=True),
    # --- Honeytoken theft ----------------------------------------------------
    Attack("Honeytoken theft", f"SELECT email, phone, ssn FROM {_CT}", "mask",
           "the honeytoken table must never surface real token values"),
]


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
