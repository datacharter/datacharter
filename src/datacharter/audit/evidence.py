"""Read, verify, and export the flight-recorder chain."""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from datacharter.audit.recorder import FLIGHT_DIR, GENESIS, canonical_hash

__all__ = ["read_entries", "verify_chain", "export_pack"]


def read_entries(
    workspace: Path | str, since: str | None = None, until: str | None = None
) -> list[dict]:
    """All entries across segments in chain order, optionally windowed by ISO ts."""
    root = Path(workspace) / FLIGHT_DIR
    out: list[dict] = []
    if not root.is_dir():
        return out
    for seg in sorted(root.glob("[0-9]*.jsonl")):
        for line in seg.read_text().splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if since and e.get("ts", "") < since:
                continue
            if until and e.get("ts", "") > until:
                continue
            out.append(e)
    return out


def verify_chain(workspace: Path | str) -> tuple[bool, int, str]:
    """Walk the full chain; returns (ok, entries_checked, detail)."""
    entries = read_entries(workspace)
    prev = GENESIS
    expected_seq = 1
    for e in entries:
        if e.get("seq") != expected_seq:
            return False, expected_seq - 1, (
                f"chain BROKEN at seq {expected_seq}: entry missing or reordered "
                f"(found seq {e.get('seq')})"
            )
        if e.get("prev") != prev:
            return False, expected_seq - 1, (
                f"chain BROKEN at seq {e['seq']}: prev-hash mismatch "
                "(an earlier entry was altered or removed)"
            )
        if canonical_hash(e) != e.get("hash"):
            return False, expected_seq - 1, (
                f"chain BROKEN at seq {e['seq']}: entry content does not match its hash "
                "(this entry was altered)"
            )
        prev = e["hash"]
        expected_seq += 1
    n = len(entries)
    head = entries[-1]["hash"][:12] if entries else "-"
    return True, n, f"{n} entries verified (head {head})"


def export_pack(
    workspace: Path | str,
    out: Path | str,
    since: str | None = None,
    until: str | None = None,
) -> Path:
    """Evidence zip: windowed entries + verification + charter-in-force + summary."""
    workspace = Path(workspace)
    out = Path(out)
    entries = read_entries(workspace, since=since, until=until)
    ok, n, detail = verify_chain(workspace)

    sessions = [e for e in entries if e.get("type") == "session"]
    accesses = [e for e in entries if e.get("type") == "access"]
    tools = Counter(a.get("tool") for a in accesses)
    relations = sorted({r for a in accesses for r in (a.get("relations") or [])})
    masked = Counter(c for a in accesses for c in (a.get("masked_columns") or []))
    errors = sum(1 for a in accesses if a.get("error"))

    summary = [
        "# Agent data-access evidence pack",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Workspace: {workspace.name}",
        f"Window: {since or 'beginning'} → {until or 'now'}",
        "",
        f"Chain verification (full log): {detail}" + ("" if ok else "  ⚠ FAILED"),
        "",
        f"- Sessions: {len(sessions)}",
        f"- Accesses: {len(accesses)}" + (f" ({errors} errored)" if errors else ""),
        "- By tool: " + (", ".join(f"{t}×{c}" for t, c in tools.most_common()) or "none"),
        "- Relations touched: " + (", ".join(relations) or "none"),
        "- Masked columns (occurrences): "
        + (", ".join(f"{c}×{n_}" for c, n_ in masked.most_common()) or "none"),
    ]

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("entries.jsonl", "\n".join(json.dumps(e, default=str) for e in entries) + "\n")
        z.writestr(
            "verification.txt",
            f"{detail}\nverified-at: {datetime.now(UTC).isoformat()}\nresult: "
            + ("OK" if ok else "FAILED") + "\n",
        )
        charter = workspace / "charter.yaml"
        z.writestr("charter.yaml", charter.read_text() if charter.exists() else "(absent)\n")
        z.writestr("summary.md", "\n".join(summary) + "\n")
    return out
