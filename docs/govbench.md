---
layout: default
title: GovBench
description: The open benchmark for AI-data governance. A frozen attack corpus, a grade A-F, and a command anyone can reproduce.
---

GovBench is a number you can cite. It fires a frozen attack battery through
the real governed tools, then grades the charter A-F. Any successful attack
is an F. Among charters that withstand every attack, the grade rewards how
much protection is actually configured.

```sh
datacharter govbench
datacharter govbench --json
datacharter govbench --min-grade B
```

Offline. Deterministic. No model, no network.

## Grade

| Grade | Meaning |
| --- | --- |
| F | At least one attack succeeded |
| D | All attacks withstood, 0-1 posture checks |
| C | All attacks withstood, 2 posture checks |
| B | All attacks withstood, 3 posture checks |
| A | All attacks withstood, 4-5 posture checks |

Posture checks: canaries armed, policies active, signed provenance, PII
declared, contract tests present. Score is 0-100. A breach caps at 49.

## Frozen corpus

**govbench-v1** · 28 attacks · sha256 `7223b8a3f4186d2ed9dd1409c9d8857f11e216bbfa0a2ca254355a4e220ec42b`

This list is the battery. Changing an attack is a new corpus id (v2), not a
quiet edit. The runner loads `src/datacharter/agent/govbench_v1.json`. The
page, the file, and `datacharter govbench --json` must agree.

Categories: PII exfiltration (7), Read-only bypass (14), Host-info disclosure (4), Policy evasion (2), Honeytoken theft (1).

- `pii-email` (PII exfiltration, mask): `SELECT email FROM local.canaries`
- `pii-lower` (PII exfiltration, mask): `SELECT lower(email) FROM local.canaries`
- `pii-concat` (PII exfiltration, mask): `SELECT email || '!' AS e FROM local.canaries`
- `pii-cast` (PII exfiltration, mask): `SELECT CAST(ssn AS VARCHAR) FROM local.canaries`
- `pii-to-json` (PII exfiltration, mask): `SELECT to_json(c) FROM local.canaries c`
- `pii-star` (PII exfiltration, mask): `SELECT * FROM local.canaries`
- `pii-alias` (PII exfiltration, mask): `SELECT phone AS contact FROM local.canaries`
- `write-multistmt` (Read-only bypass, refuse): `SELECT 1; DROP TABLE local.canaries`
- `write-drop-canary` (Read-only bypass, refuse): `DROP TABLE local.canaries`
- `write-drop-snapshot` (Read-only bypass, refuse): `DROP TABLE IF EXISTS local.snapshot_x`
- `write-replace` (Read-only bypass, refuse): `CREATE OR REPLACE TABLE local.canaries AS SELECT 1`
- `write-create` (Read-only bypass, refuse): `CREATE TABLE evil AS SELECT 1`
- `write-delete` (Read-only bypass, refuse): `DELETE FROM local.canaries`
- `write-update` (Read-only bypass, refuse): `UPDATE local.canaries SET email = 'x'`
- `write-copy` (Read-only bypass, refuse): `COPY (SELECT 1) TO 'pwned.csv'`
- `write-install` (Read-only bypass, refuse): `INSTALL httpfs`
- `write-attach` (Read-only bypass, refuse): `ATTACH 'x.db' AS x`
- `write-pragma` (Read-only bypass, refuse): `PRAGMA database_list`
- `write-read-csv` (Read-only bypass, refuse): `SELECT * FROM read_csv('/etc/passwd')`
- `write-read-text` (Read-only bypass, refuse): `SELECT read_text('/etc/passwd')`
- `host-databases` (Host-info disclosure, refuse): `SELECT * FROM duckdb_databases()`
- `host-secrets` (Host-info disclosure, refuse): `SELECT * FROM duckdb_secrets()`
- `host-settings` (Host-info disclosure, refuse): `SELECT value FROM duckdb_settings() WHERE name='temp_directory'`
- `host-secret-directory` (Host-info disclosure, refuse): `SELECT current_setting('secret_directory')`
- `write-case-comment` (Read-only bypass, refuse): `sElEcT 1 /* x */ ; delete from local.canaries`
- `policy-raw-email` (Policy evasion, refuse): `SELECT email FROM store.customers`
- `policy-list-email` (Policy evasion, refuse): `SELECT list(email) FROM store.customers`
- `honey-select` (Honeytoken theft, mask): `SELECT email, phone, ssn FROM local.canaries`

`expect=mask` means the result must be masked (or refused). `expect=refuse`
means the query must error. Policy-evasion rows run only when the charter
has a policy.

Cite a run as: GovBench govbench-v1, sha256 7223b8a3f4186d2ed9dd1409c9d8857f11e216bbfa0a2ca254355a4e220ec42b, grade X.

See [the Gauntlet](cli.html#redteam-directory) (`datacharter redteam`) for
the same battery without the grade.
