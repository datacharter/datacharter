---
title: A local DuckDB UI — editor, charts, and profiling in one window
description: DataCharter is a free, open-source DuckDB UI — a local SQL editor with live results, one-click charts, data profiling, and federated queries across files and databases. pip install datacharter.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

If you love DuckDB and want a proper UI on top of it — an editor, results you
can see, charts, profiling — DataCharter gives you exactly that in one
`pip install`, and keeps everything on your machine.

```sh
uvx datacharter serve
# -> a full DuckDB workspace on http://127.0.0.1:8321, demo data included
```

## What you get on top of DuckDB

DuckDB is the engine; DataCharter is the cockpit:

- **A real SQL editor** (Monaco, the VS Code editor) with DuckDB syntax,
  ⌘/Ctrl+Enter to run, and **live results that preview as you type**.
- **One-click charts** — auto-detected from your result shape, powered by
  Vega-Lite, no chart-builder ceremony.
- **A profiling panel** — missing values, distributions, percentiles,
  outliers, and per-column top-value bars for any result.
- **Query history and saved queries** — every run is kept locally; reopen or
  share the `.sql` file from your workspace.
- **Drag-and-drop files** — drop a CSV, Parquet, JSON, or Excel file on the
  window and it's queryable instantly.
- **EXPLAIN and scan estimates** — see the plan, and get warned before a
  query scans a mountain of data.
- **Exports** — CSV, Parquet, JSON, XLSX, one click.

## Not just local files: federation

Because it's DuckDB underneath, one SQL statement can join across sources:
local files next to **Postgres, MySQL, SQLite, SQL Server, Snowflake,
BigQuery, Iceberg, and Delta** — configured in a small [charter.yaml](charter-yaml.html)
file with credentials kept in your OS keychain or `.env`. See
[Sources](sources.html) for the full list.

## And it's read-only by construction

The engine refuses writes, DDL, and filesystem access at the query layer —
so pointing it (or a teammate, or an AI agent) at your production replica
can't do damage. If you later want an agent in the loop, the same workspace
adds [governed, PII-masked agent access](agent.html) and a
[governed MCP server](mcp-data-governance.html) — but the UI is a great
DuckDB companion even if you never touch the agent side.

## Try it

Nothing to configure, nothing global:

```sh
uvx datacharter serve      # ephemeral demo workspace
```

or start [a real workspace over your own data](quickstart.html) in a couple
of minutes. It's Apache-2.0, local-first, and
[open source on GitHub](https://github.com/datacharter/datacharter) — come
say hi if it makes your DuckDB day nicer.
