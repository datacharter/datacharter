---
title: Trust & security — DataCharter
description: How DataCharter is built to be trustworthy — local-first architecture, a governed read-only surface, verifiable answers, a hardened supply chain, and a clear disclosure path.
---

[Home](index.html) &middot; [Security](security.html) &middot; [Provenance](provenance.html) &middot; [Audit](audit.html) &middot; [Privacy](privacy.html) &middot; [About](about.html)

# Trust & security

DataCharter governs how AI agents touch your data. That only works if DataCharter
itself is trustworthy — so this page lays out, in one place, how it is built,
what it guarantees, and how to report a problem. Nothing here asks you to take our
word for it; wherever we can, the claim is something you can verify.

## Architecture: there is no data plane to breach

DataCharter runs **on your machine or in your infrastructure**. Your data stays in
your sources; queries run locally through DuckDB. The open-source tool sends **no
telemetry** and phones home to nothing. There is no DataCharter-operated service
that ever sees your rows — which means the largest class of vendor risk simply
does not exist here.

## The governed surface is enforced, not cosmetic

Every agent — the built-in chat, Claude Desktop, Cursor, Cline, Claude Code over
MCP — reaches your data through the same governed tools, where:

- **The engine is read-only.** A parser-based guard refuses any write, DDL, DML,
  or filesystem/remote function. The agent surface additionally cannot run
  `local.*` DDL.
- **PII is masked, and the mask is enforced.** A masked column may appear in a
  `SELECT` list but not in `WHERE`/`JOIN`/`ORDER BY`/a subquery, so values can't
  be inferred by conditioning on them. Row-level filters restrict which rows an
  agent sees.
- **Untrusted data is quarantined.** Result cells are scanned for prompt-injection
  payloads and neutralized before the model sees them — protection at the data
  plane, where nothing else looks.
- **Every access is recorded.** An append-only, hash-chained audit trail logs each
  query, the columns masked, row counts, and a hash of the result — tamper-evident
  and exportable as evidence.

## Verifiable answers

A governed answer can be sealed into a **signed receipt** binding it to the exact
query, rows, policy version, and model — and anyone can verify it offline with a
[single zero-dependency script](https://raw.githubusercontent.com/datacharter/datacharter/main/tools/verify_receipt.py),
no DataCharter install required. See [Provenance](provenance.html).

## A hardened supply chain

Every release is built in GitHub Actions via PyPI Trusted Publishing (OIDC) — no
long-lived tokens — and ships **PEP 740 provenance attestations** (Sigstore-signed).
The repository runs, on every change:

- **CodeQL** static analysis (Python + TypeScript)
- **Dependency audit** (`pip-audit`) and a **CycloneDX SBOM**
- **Secret scanning** (gitleaks) across the full history
- **Dependabot** for pip, npm, and GitHub Actions

The enterprise server image additionally carries an SBOM and SLSA provenance, is
**signed with Sigstore/cosign**, and is scanned with Trivy for fixable
HIGH/CRITICAL vulnerabilities.

## Reporting a vulnerability

Please report security issues **privately** through GitHub's private vulnerability
reporting — the repository's **Security → Advisories → Report a vulnerability**.
Do not open a public issue. We aim to acknowledge within three business days. Our
machine-readable contact is at
[`/.well-known/security.txt`](/.well-known/security.txt); the full policy and scope
live in [Security](security.html).

## Enterprise & compliance

DataCharter Team (the self-hosted enterprise edition) adds per-identity
authorization, identity-bound provenance receipts, SIEM-ready structured logs, and
a hardened container. Because it runs entirely inside your infrastructure and holds
no customer data of its own, the relevant audit boundary is the software and its
release pipeline. A SOC 2 readiness assessment is complete; reach out for the
current security package (whitepaper, SBOM, and pen-test summary).
