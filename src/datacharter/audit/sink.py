"""SIEM sinks for flight-recorder events. Metadata only, never raw rows.

Off unless DATACHARTER_AUDIT and/or DATACHARTER_OTLP_ENDPOINT is set. The hash
chain stays the source of truth; these sinks copy the same event outbound.
"""

from __future__ import annotations

import json
import os
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "AuditSink",
    "FanoutSink",
    "JsonAuditSink",
    "OtlpAuditSink",
    "bind_principal",
    "current_principal",
    "reset_principal",
    "siem_event",
    "sink_from_env",
]

_ENV_JSON = "DATACHARTER_AUDIT"
_ENV_OTLP = "DATACHARTER_OTLP_ENDPOINT"
_DROP = frozenset({"rows"})
_principal: ContextVar[str] = ContextVar("datacharter_audit_principal", default="")


class AuditSink(Protocol):
    def record(self, event: dict) -> None: ...


def bind_principal(subject: str | None) -> Token:
    """Bind the authenticated subject for this task. Reset with reset_principal."""
    return _principal.set((subject or "").strip())


def reset_principal(token: Token) -> None:
    _principal.reset(token)


def current_principal() -> str:
    return _principal.get()


def siem_event(entry: dict) -> dict:
    """Copy a chain entry for SIEM: drop rows, add allow/deny on access."""
    event = {k: v for k, v in entry.items() if k not in _DROP}
    if event.get("type") == "access":
        err = str(event.get("error") or "")
        if "not authorized" in err.lower():
            event["decision"] = "deny"
        elif err:
            event["decision"] = "error"
        else:
            event["decision"] = "allow"
    return event


class JsonAuditSink:
    """One JSON object per line to a stream or file."""

    def __init__(self, dest: Any = None) -> None:
        self._dest = sys.stderr if dest is None else dest

    def record(self, event: dict) -> None:
        line = json.dumps(event, default=str) + "\n"
        dest = self._dest
        try:
            if isinstance(dest, (str, Path)):
                path = Path(dest)
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a") as f:
                    f.write(line)
            else:
                dest.write(line)
                flush = getattr(dest, "flush", None)
                if flush is not None:
                    flush()
        except Exception:
            return


class OtlpAuditSink:
    """OTLP HTTP JSON logs. POST {endpoint}/v1/logs. Never sends raw rows."""

    def __init__(self, endpoint: str, *, post=None, headers: dict | None = None) -> None:
        self.url = _logs_url(endpoint)
        self._post = post or _httpx_post
        self._headers = headers

    def record(self, event: dict) -> None:
        try:
            self._post(self.url, _otlp_envelope(siem_event(event)), self._headers)
        except Exception:
            return


class FanoutSink:
    """Call every sink. One failure does not skip the rest."""

    def __init__(self, sinks: list[AuditSink]) -> None:
        self._sinks = list(sinks)

    def record(self, event: dict) -> None:
        for sink in self._sinks:
            try:
                sink.record(event)
            except Exception:
                continue


def sink_from_env() -> AuditSink | None:
    """Json and/or OTLP from env. Unset means no SIEM sink (chain still on)."""
    sinks: list[AuditSink] = []
    spec = (os.environ.get(_ENV_JSON) or "").strip()
    if spec == "json":
        sinks.append(JsonAuditSink(sys.stderr))
    elif spec.startswith("json:"):
        path = spec[5:].strip()
        if path:
            sinks.append(JsonAuditSink(path))
    endpoint = (os.environ.get(_ENV_OTLP) or "").strip()
    if endpoint:
        sinks.append(OtlpAuditSink(endpoint))
    if not sinks:
        return None
    if len(sinks) == 1:
        return sinks[0]
    return FanoutSink(sinks)


def _logs_url(endpoint: str) -> str:
    url = endpoint.strip().rstrip("/")
    if url.endswith("/v1/logs"):
        return url
    return url + "/v1/logs"


def _httpx_post(url: str, payload: dict, headers: dict | None = None) -> None:
    import httpx

    httpx.post(url, json=payload, headers=headers, timeout=2.0)


def _unix_nano(ts: str | None) -> str:
    if not ts:
        return str(int(datetime.now(UTC).timestamp() * 1_000_000_000))
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1_000_000_000))
    except ValueError:
        return str(int(datetime.now(UTC).timestamp() * 1_000_000_000))


def _otlp_envelope(event: dict) -> dict:
    record: dict[str, Any] = {
        "timeUnixNano": _unix_nano(event.get("ts") if isinstance(event.get("ts"), str) else None),
        "severityText": "WARN" if event.get("decision") == "deny" else "INFO",
        "body": {"stringValue": json.dumps(event, default=str, separators=(",", ":"))},
        "attributes": [],
    }
    attrs = record["attributes"]
    for key, otel_key in (
        ("type", "audit.type"),
        ("tool", "audit.tool"),
        ("decision", "audit.decision"),
        ("principal", "audit.principal"),
        ("session", "audit.session"),
    ):
        val = event.get(key)
        if val:
            attrs.append({"key": otel_key, "value": {"stringValue": str(val)}})
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "datacharter"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "datacharter.audit"},
                        "logRecords": [record],
                    }
                ],
            }
        ]
    }
