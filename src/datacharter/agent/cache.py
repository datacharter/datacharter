"""NL→SQL cache: reuse the SQL a question produced, keyed by contract fingerprint.

A repeat or (after normalization) reworded question reuses the cached SQL and the
agent re-runs it on *current* data — skipping the LLM round-trip while staying
fresh. The cache is invalidated whenever the contract changes (fingerprint).
Embedding-based semantic similarity (catching deeper rewordings) is a follow-up;
this handles exact and normalized repeats with no extra dependency or endpoint.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

__all__ = ["AnswerCache", "contract_fingerprint"]


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", question.lower())).strip()


def contract_fingerprint(sources: list) -> str:
    """Stable hash of the contract shape; changes invalidate the whole cache."""
    material = json.dumps(
        [[s.name, s.type.value, sorted(s.tables), s.pii] for s in sources], sort_keys=True
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


class AnswerCache:
    """Persistent normalized-question → SQL map, scoped to a contract fingerprint."""

    def __init__(self, path: Path, fingerprint: str) -> None:
        self._path = path
        self._fingerprint = fingerprint
        self._data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError):
            return {"fingerprint": self._fingerprint, "entries": {}}
        if data.get("fingerprint") != self._fingerprint:  # contract changed — drop it
            return {"fingerprint": self._fingerprint, "entries": {}}
        return data

    def get(self, question: str) -> str | None:
        return self._data.get("entries", {}).get(_normalize(question))

    def put(self, question: str, sql: str) -> None:
        self._data.setdefault("entries", {})[_normalize(question)] = sql
        self._data["fingerprint"] = self._fingerprint
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data))
