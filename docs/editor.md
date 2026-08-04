---
title: The workbench — SQL editor, live results, charts, and profiling
description: DataCharter's local UI — a Monaco SQL editor with live-as-you-type results, one-click charts, a column profiler, query history, a command palette, drag-and-drop files, and exports.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

Everything on this page works with **no AI configured** — the workbench is a
complete local SQL tool on its own. `datacharter serve`, open the URL, explore.

## The editor

A Monaco editor (the VS Code editor) with DuckDB SQL, catalog-aware
autocomplete, and **live results**: a beat after you stop typing, the query
runs automatically (row-capped, silent on error) so results track your typing.
`Cmd/Ctrl+Enter` or **Run** executes the full query. Every run lands in a
local **history** you can reopen, and **Save** keeps named queries in your
workspace's `queries/` directory — plain `.sql` files, committed with the
contract.

## Results show their work

Under every result: the row count and **Reads …** — the exact source columns
the query touched (provenance), with per-output-column lineage available via
[`datacharter lineage`](cli.html). Flip **Agent view** to re-render the same
result exactly as an agent would receive it — masked columns, row filters,
policies applied.

## Charts

The **Chart** tab auto-detects a chart from your result's column types —
dates + numbers become a line, categories + numbers a bar, two numbers a
scatter — and captions it. Override the type (bar, line, area, scatter, pie)
and the x/y columns from the dropdowns. Charts are Vega-Lite underneath; the
agent can emit chart specs into the same panel.

## Profile

The **Profile** tab summarizes every column of a result in one pass: nulls,
distinct counts, quartiles, standard deviation, and per-column top-value bars.
It's the "what am I even looking at" button for an unfamiliar table.

## Know the cost before you run

**Estimate** predicts how many rows a query will scan and warns before a big
one; **Explain** shows the engine's plan. Both live next to the Run button.

## Files, snapshots, exports

Drag a CSV, Parquet, JSON, or Excel file onto the window and it's queryable
instantly (uploads are copied into the workspace and capped at **2 GB** —
for bigger files, add them as a [source](sources.html) instead: that registers
the file in place, no copy, no size limit, with pushdown). **Snapshot** saves a result as a reusable `local.<name>` table —
each snapshot in the sidebar has a **recheck** button that re-runs its query
and tells you inline whether the numbers changed. **Export** writes a result
to CSV, Parquet, JSON, or XLSX — in Agent view, exports are masked too.

## Command palette

`Cmd/Ctrl+K` jumps anywhere: tables, saved queries, panels, actions — and any
contract-defined [metric](charter-yaml.html#metrics) ("Run metric: revenue"
compiles it to SQL and runs it). The fastest way around once you know it
exists.

Next: [The workspace on disk →](workspace.html)
