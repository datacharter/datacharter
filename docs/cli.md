---
title: CLI reference
description: Every datacharter command, with usage and options.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

Every command takes an optional workspace `directory` (default: the current one).
Run `datacharter <command> --help` for the exact flags.

## Setup

### `init [directory] [--demo] [--force]`
Scaffold a workspace: `charter.yaml`, `queries/`, `.env.example`, `.gitignore`.
`--demo` includes a generated demo dataset; `--force` overwrites an existing
`charter.yaml`.

### `serve [directory]`
Start the local web app (API + UI) on `http://127.0.0.1:8321`.

| Flag | Effect |
| --- | --- |
| `--host` | Bind address (default `127.0.0.1`, localhost only). |
| `--port` | Port (default `8321`). |
| `--local` | Use a local Ollama model for the agent. |
| `--model` | Model name to use with `--local`. |
| `--no-spill` | Fail queries instead of spilling to disk (regulated environments). |
| `--offline` | No-egress mode: disable the LLM agent and write a no-egress attestation. |

In the UI, flip **Agent view** on any result to preview it with PII columns
masked — exactly what the agent and the [MCP server](mcp.html) see.

### `secrets set|list|rm <name>`
Manage `${NAME}` secrets in the OS keyring. `set` prompts without echo (or pass
`--value`); `list` shows names only; `rm` removes one.

## Explore and govern

### `mcp [directory] [--serve-url URL]`
Run a [Model Context Protocol](mcp.html) server over stdio, exposing the four
governed query tools to any MCP client — read-only, PII-masked. With
`--serve-url`, the server proxies tool calls to an already-running
`datacharter serve` instead of opening its own engine (this is how the in-app
Claude Code integration bridges to the governed toolbox); without it, it opens
the workspace directly.

### `diff <left> <right> [directory] [--key cols]`
Diff two relations across sources: rows only in each side plus the common count.
With `--key`, rows are matched by key and changed rows are counted separately.

### `explain <sql> [directory]`
Show a query's plan and `~N rows` estimates **without running it** — a pre-flight
cost check.

### `query <sql> [directory] [--format table|csv|json]`
Run a read-only SQL query across your sources and print the result — federated
joins, the same read-only guard as the app. `--format` selects table (default),
CSV, or JSON output.

### `sample <relation> [directory] [--rows N]`
Print a PII-masked CSV sample of a relation (contract PII columns come back as
`•••`), safe to paste into a ticket. Default 10 rows.

### `scan [directory] [--write]`
Suggest PII columns for `charter.yaml` by column name and by sampled values.
`--write` merges the suggestions into `charter.yaml` (round-trip; credential
references are left untouched).

### `drift [directory]`
Report schema drift: declared tables or PII columns that no longer exist in the
live sources (a missing PII column is a masking gap). Exits non-zero on drift —
usable as a CI gate.

### `metric <name> [directory] [--by cols] [--grain g]`
Run a contract-defined [metric](charter-yaml.html#metrics) — a named aggregation
declared under `metrics:` — resolved to one governed query. `--by` overrides the
grouping dimensions; `--grain day|week|month|quarter|year` groups by a
`date_trunc` of the metric's `time_column`.

### `test [directory] [--select name]`
Run the [data assertions](charter-yaml.html#tests) declared under `tests:` and
**exit non-zero if any fail** — for CI. `--select` runs one test by name.

### `lineage [directory] [--relation R] [--json]`
Show cross-source lineage aggregated from your local query history: which
relations get read together, and which output columns derive from which inputs.
`--relation` filters to one relation; `--json` emits the graph for tooling.
History is recorded as you run queries in the app.

### `snapshot <name> <sql> [directory]`
Save a query's result as `local.<name>` along with its SQL.

### `recheck <name> [directory]`
Re-run a snapshot's query on current data and diff it against the saved result —
"did this number change?". Exits non-zero when the result has changed.
