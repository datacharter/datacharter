# Security Policy

DataCharter treats several of its boundaries as security-critical: the
parser-based read-only guard, contract-driven PII masking, credential scrubbing
on every error path, and encrypted local spill/state. We appreciate reports that
help keep those boundaries sound.

## Reporting a vulnerability

Please report security issues **privately** through GitHub's private vulnerability
reporting — open the repository's **Security → Advisories → Report a vulnerability**.
Do not open a public issue for a security report.

We aim to acknowledge a report within three business days and to keep you updated
as we investigate and ship a fix.

## Supported versions

DataCharter is pre-1.0; security fixes land on the latest release. Please run the
most recent version (`pip install -U datacharter`).

## Scope

In scope:

- Bypasses of the read-only guard — any way to run a write, DDL/DML, or a
  filesystem/remote function through a query.
- PII-mask bypasses — surfacing a masked column's raw values through the agent
  tools or the MCP server.
- Credential leakage in error messages, logs, or on disk.
- The HTTP surface of `datacharter serve` — DNS-rebinding (Host header) or
  cross-site (CSRF) weaknesses.

Out of scope:

- Issues that require an already-compromised local machine or account.
- The behavior or vulnerabilities of the third-party sources you choose to
  connect to.
