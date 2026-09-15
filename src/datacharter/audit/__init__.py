"""Flight recorder: tamper-evident audit of agent data access."""

from datacharter.audit.recorder import FLIGHT_DIR, GENESIS, FlightRecorder, canonical_hash
from datacharter.audit.sink import (
    AuditSink,
    FanoutSink,
    JsonAuditSink,
    OtlpAuditSink,
    bind_principal,
    siem_event,
    sink_from_env,
)

__all__ = [
    "FlightRecorder",
    "canonical_hash",
    "GENESIS",
    "FLIGHT_DIR",
    "AuditSink",
    "FanoutSink",
    "JsonAuditSink",
    "OtlpAuditSink",
    "bind_principal",
    "siem_event",
    "sink_from_env",
]
