---
title: An open-source, local-first alternative to Hex
description: Looking for an open-source Hex alternative? DataCharter is a free, local SQL workspace with charts, profiling, and governed AI-agent access — no cloud, no per-seat pricing, your data never leaves your machine.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

First, credit where it's due: Hex is a genuinely lovely product — collaborative
notebooks, polished AI features, great for teams that want analytics in the
cloud. If that's what you need, use Hex.

DataCharter sits in a different spot, and for a lot of individual data work
it's the spot that matters: **everything runs on your laptop, nothing leaves
it, and it's free, open source (Apache-2.0), and yours.**

## When DataCharter is the better fit

- **Your data can't go to a SaaS.** Client data, regulated data, or just
  data you'd rather keep local. DataCharter's engine, UI, and agent all run
  as one local process — there is no cloud side.
- **You want SQL-first exploration, not notebooks.** A Monaco SQL editor
  with live-as-you-type results, one-click charts, and a profiling panel —
  no cells, no kernel, no publish step.
- **You query files and databases together.** DuckDB federation joins a
  local CSV to a Snowflake table to Parquet in S3 in one statement — see
  [Sources](sources.html).
- **You want AI help without handing over the keys.** Connect Claude Code,
  a local Ollama model, or any OpenAI-compatible agent — with access
  declared per source, table, and column in a
  [data contract](charter-yaml.html), PII masked by default, an
  [audit trail](audit.html) of every access, and
  [clean-room-style policies](policies.html) like "aggregates only" and
  "groups of at least 10".
- **Zero procurement.** `pip install datacharter` (or `uvx datacharter`)
  and you're exploring in under a minute — no accounts, no seats, no trial
  clock.

## When Hex is the better fit

Honesty corner: if you need real-time multiplayer collaboration, published
interactive apps for stakeholders, scheduled runs in the cloud, or
Python/R notebooks as the primary medium — that's Hex's home turf, and
DataCharter doesn't try to be that.

## Try the local-first version of the idea

```sh
uvx datacharter serve
# -> a governed local workspace with demo data on http://127.0.0.1:8321
```

Then point it at [your own data](quickstart.html). It's
[open source](https://github.com/datacharter/datacharter) — if you take it
for a spin and something feels missing, tell us; the roadmap is built from
exactly that.
