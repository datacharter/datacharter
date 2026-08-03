---
title: A governed MCP server for your databases — safe AI access to real data
description: Give Claude, Cursor, or any MCP client read-only, PII-masked SQL over Postgres, Snowflake, files, and more. Access is declared in a data contract; every query is audit-logged. Local, open source.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

Connecting an AI agent straight to your database is a leap of faith: most MCP
database servers hand the model whatever the connection string can see.
DataCharter's MCP server takes the opposite stance — **the agent gets exactly
what your data contract grants, and not one column more.**

```sh
uvx datacharter mcp <workspace>
# stdio MCP server: list_sources · list_tables · describe_table · query
```

Works with **Claude Code, Claude Desktop, Cursor, Cline, Continue, Goose** —
anything that speaks MCP. Setup recipes per client are on the
[MCP page](mcp.html).

## What "governed" means here, concretely

- **Read-only by construction.** The engine refuses writes, DDL, and
  filesystem access at the query layer — not by prompt, by parser. A
  misbehaving agent can't `DROP`, `UPDATE`, or exfiltrate a file.
- **Access is declared, not assumed.** A [charter.yaml](charter-yaml.html)
  data contract grants access per **source → table → column**. PII is
  auto-detected and defaults to *no agent access*; the agent sees `•••`
  unless you explicitly grant the field.
- **Policies enforced by query analysis.** One YAML line gets you
  clean-room-style rules — `aggregates only`, `groups of at least 10`
  (k-anonymity suppression), join limits. See [Policies](policies.html).
- **Every access is recorded.** A tamper-evident, hash-chained
  [flight recorder](audit.html) logs each agent query with dual attribution
  and masked-column detail — `datacharter audit verify` proves the chain,
  and one command exports an evidence pack.
- **Canary tripwires, if you want them.** Fake PII rows whose unique tokens set
  off a tamper-evident alarm if they ever appear in agent output — opt-in canaries plant honeytokens behind
  the mask; if one ever appears in agent output you get a tamper-evident
  alarm, and block mode withholds the response.
- **Context travels with the contract.** Markdown guides in `guides/*.md`
  ("revenue is net of refunds") reach every MCP client automatically, and
  [agent evals](evals.html) measure whether they actually help.

## One governance layer, many sources

The same contract governs local CSV/Parquet/JSON/Excel files and
**Postgres, MySQL, SQLite, SQL Server, Snowflake, BigQuery, Iceberg, Delta**
— federated by DuckDB, so the agent can join across them in one governed
query. Full list on [Sources](sources.html).

## See what the agent sees

Run `datacharter serve` and flip on **Agent view** in the UI: it shows,
column by column, exactly what comes back through the MCP tools — masked
fields and all. It's the fastest way to convince yourself (or your security
team) that the leash holds.

## Try it in two minutes

```sh
uvx datacharter init myws --demo
uvx datacharter mcp myws        # add to your MCP client of choice
```

Recipes for each client are on the [MCP page](mcp.html), and the whole thing
is [Apache-2.0 on GitHub](https://github.com/datacharter/datacharter). If
your agent setup needs a governance story we haven't covered, open an issue
— that's how the policies feature got built.
