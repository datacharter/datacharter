---
title: Security & privacy posture
description: How DataCharter protects your data, credentials, and machine.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)


# Security & privacy posture

DataCharter runs on your machine, against your data. Here is exactly what it
does — and doesn't — do.

## No telemetry

Zero. DataCharter makes no analytics, crash-reporting, or "phone-home" calls of
any kind. The server binds to `127.0.0.1` (localhost) by default; `--host` is an
explicit opt-in for network exposure.

## The engine is read-only

Queries run through a guard that uses DuckDB's own parser to accept **only**:

- a single `SELECT` (or `WITH … SELECT`, `VALUES`, `SHOW`, `DESCRIBE`,
  `SUMMARIZE`),
- `EXPLAIN` of such a query, and
- `CREATE`/`DROP TABLE local.*` — the one write path, into your local scratch
  catalog.

Everything else — `DELETE`/`UPDATE`/`INSERT`, `COPY`, `ATTACH`, `INSTALL`,
`SET`, multiple statements, and filesystem/remote functions like `read_csv` or
`postgres_scan` — is rejected. Sources are reached only through the views the
engine registers from your `charter.yaml`, never through ad-hoc readers in a
query. Because the check is the parser (not a text filter), comment, quote, and
dollar-quote tricks don't get past it.

## Agent access is enforced, not display-only

For the agent, MCP, and Claude Code surfaces, a masked column may appear only in
the `SELECT` list (its values return as `•••`). Using it in `WHERE`, `JOIN`,
`GROUP BY`, `ORDER BY`, or a subquery is refused, so a model cannot infer masked
values by conditioning results on them (e.g. `WHERE email = '…'` or
`ORDER BY email`). The refusal is fail-closed and reuses the same parser the
read-only guard uses. This does not apply to the local human SQL editor, which
returns real values.

Row-level security is available too: `row_filters` in `charter.yaml` restrict the
agent to specific rows per table (its queries are rewritten to honor the filter,
fail-closed). Again, the human SQL editor is unaffected.

## Credentials never touch disk in the clear

- `charter.yaml` may only reference secrets as `${NAME}`; literal secret values
  are a hard error. Secrets resolve from the environment, a workspace `.env`, or
  the OS keyring (`datacharter secrets set NAME`).
- Inside DuckDB, credentials are injected as **temporary** secrets (in-memory);
  DataCharter never writes a persistent DuckDB secret.
- Error messages are scrubbed of secret values before they surface.

## Disk-spill hygiene

Large queries can spill to disk. DataCharter contains and protects those spills:

- `temp_directory` is pinned to `.datacharter/tmp/`, and
  `temp_file_encryption` is always on — spill files use ephemeral keys, so
  leftover blocks after a crash are cryptographically unreadable.
- The temp directory is wiped on startup and shutdown.
- The local state DB (`.datacharter/state.duckdb`, holding saved snapshots) is
  encrypted with a key from your OS keyring (or `DATACHARTER_STATE_KEY`).
- `serve --no-spill` disables disk spilling entirely for regulated environments.

Full-disk encryption (FileVault/BitLocker) and OS swap are outside DataCharter's
control and remain the complementary defense.

## The local server

The API listens on localhost. Even so, a browser page you visit could try to
reach it, so DataCharter:

- rejects requests whose `Host` header isn't loopback (defeats DNS-rebinding),
  and
- rejects cross-site browser requests via `Origin` / `Sec-Fetch-Site` checks.

Non-browser clients (curl, scripts) on your machine can still call the API.

## Reporting an issue

Found a security problem? Please open a GitHub issue (or contact the
maintainers privately for anything sensitive) rather than posting an exploit
publicly.
