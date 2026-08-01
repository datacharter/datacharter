"""Append-only, hash-chained audit of agent data access. Metadata + hashes only.

Every entry carries the previous entry's hash (`prev`) and its own SHA-256 over
the canonicalized body, so any edit or deletion is detectable by re-walking the
chain (`datacharter audit verify`). The log stores what an agent DID — SQL,
columns, masking, row counts, a hash of the exact result it saw — never raw rows,
so the audit trail cannot become a second PII store.
"""

from __future__ import annotations

import fcntl
import getpass
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["FlightRecorder", "canonical_hash", "GENESIS", "FLIGHT_DIR"]

FLIGHT_DIR = ".datacharter/flight"
GENESIS = "0" * 64
_SEGMENT_MAX_BYTES = 10 * 1024 * 1024


def canonical_hash(entry: dict) -> str:
    """SHA-256 over the canonical JSON of the entry without its `hash` field."""
    body = {k: v for k, v in entry.items() if k != "hash"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


class FlightRecorder:
    """Writes session + access entries; failure-safe (never breaks a query)."""

    def __init__(self, workspace: Path | str, enabled: bool = True) -> None:
        self._dir = Path(workspace) / FLIGHT_DIR
        self._enabled = enabled
        self._session = ""

    def start_session(
        self,
        surface: str,
        *,
        client: dict | None = None,
        model: str | None = None,
        question: str | None = None,
    ) -> str:
        if not self._enabled:
            return ""
        self._session = uuid.uuid4().hex[:12]
        self._append({
            "type": "session", "session": self._session, "surface": surface,
            "user": _os_user(), "client": client, "model": model, "question": question,
        })
        return self._session

    def record_alarm(self, tool: str, arguments: str, token: str) -> None:
        """A canary token surfaced in agent-bound output — record the tripwire hit."""
        if not self._enabled:
            return
        try:
            args = json.loads(arguments or "{}")
        except ValueError:
            args = {}
        self._append({
            "type": "alarm", "kind": "canary", "session": self._session,
            "tool": tool, "sql": args.get("sql"), "token": token,
        })

    def record_access(self, tool: str, arguments: str, result: str) -> None:
        if not self._enabled:
            return
        try:
            args = json.loads(arguments or "{}")
        except ValueError:
            args = {}
        entry: dict = {
            "type": "access", "session": self._session, "tool": tool,
            "sql": args.get("sql"), "relation": args.get("relation"),
        }
        if result.startswith("Error:"):
            entry.update(
                error=result, row_count=None, truncated=None,
                masked_columns=[], relations=[], result_sha256=None,
            )
        else:
            entry.update(
                error=None,
                result_sha256=hashlib.sha256(result.encode()).hexdigest(),
                **_parse_result(result),
            )
        self._append(entry)

    # -- internals ------------------------------------------------------------

    def _append(self, body: dict) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with open(self._dir / ".lock", "w") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)
                seg, prev, seq = self._tail()
                entry = {
                    "seq": seq + 1,
                    "ts": datetime.now(UTC).isoformat(),
                    **body,
                    "prev": prev,
                }
                entry["hash"] = canonical_hash(entry)
                with open(seg, "a") as f:
                    f.write(json.dumps(entry, default=str) + "\n")
        except Exception:  # auditing must never break a query
            return

    def _tail(self) -> tuple[Path, str, int]:
        """Segment to append to + last (hash, seq); rotates when the tail is full."""
        segs = sorted(self._dir.glob("[0-9]*.jsonl"))
        if not segs:
            return self._dir / "000001.jsonl", GENESIS, 0
        prev, seq = GENESIS, 0
        for s in reversed(segs):
            with open(s) as f:
                for line in f:
                    if line.strip():
                        e = json.loads(line)
                        prev, seq = e["hash"], e["seq"]
            if seq:
                break
        last = segs[-1]
        if last.stat().st_size >= _SEGMENT_MAX_BYTES:
            return self._dir / f"{int(last.stem) + 1:06d}.jsonl", prev, seq
        return last, prev, seq


def _os_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _parse_result(result: str) -> dict:
    """Best-effort metadata from the rendered result the agent saw."""
    try:
        p = json.loads(result)
    except ValueError:
        return {"row_count": None, "truncated": None, "masked_columns": [], "relations": []}
    if not isinstance(p, dict):
        return {"row_count": None, "truncated": None, "masked_columns": [], "relations": []}
    prov = p.get("provenance") or {}
    return {
        "row_count": p.get("row_count"),
        "truncated": p.get("truncated"),
        "masked_columns": p.get("masked_columns") or [],
        "relations": list(prov.get("relations") or []) if isinstance(prov, dict) else [],
    }
