"""Persist eval runs to a local ledger and read the trend."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

from datacharter.agent.eval_runner import RunRecord

_LEDGER = ".datacharter/eval-runs"


def save_run(workspace: Path, record: RunRecord) -> Path:
    d = workspace / _LEDGER
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    payload = dataclasses.asdict(record)
    payload["started_at"] = now.isoformat()
    path = d / f"{now.strftime('%Y%m%dT%H%M%S%f')}.json"
    path.write_text(json.dumps(payload, default=str, indent=2))
    return path


def load_history(workspace: Path) -> list[dict]:
    d = workspace / _LEDGER
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (ValueError, OSError):
            continue
    return out


def regression_diff(prev: dict, curr: dict) -> list[str]:
    def passed(record: dict) -> dict:
        return {c["question"]: c["with_guides"]["passed"] for c in record.get("cases", [])}

    p, c = passed(prev), passed(curr)
    return [q for q, ok in p.items() if ok and not c.get(q, False)]
