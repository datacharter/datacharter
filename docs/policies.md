---
title: Policies — plain English, enforced math
description: Aggregate-only access, k-anonymity group suppression, and join limits — written the way you'd say them, enforced by query analysis.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

Masking hides sensitive *columns*. Sometimes the requirement is stronger: agents
should never see **individuals at all** — only statistics, only over groups big
enough that nobody can be reverse-engineered. That's the control data clean
rooms sell (Google's Ads Data Hub won't return a row unless ≥50 users are behind
it). DataCharter gives you the same class of control in one YAML block, written
the way you'd say it:

```yaml
policies:
  crm.customers:
    - aggregates only
    - groups of at least 10
    - no joins to payments
```

The sentences compile deterministically — no model, no ambiguity; an
unrecognized sentence is a load error. Prefer explicit keys? Same meaning:

```yaml
policies:
  crm.customers:
    aggregate_only: true
    min_group_size: 10
    no_joins_to: [payments]
```

## What each rule enforces (agent surface only)

- **`aggregates only`** — a query touching the relation must be a single plain
  aggregate SELECT (aggregate functions, GROUP BY welcome). Raw rows, DISTINCT,
  CTEs, and set operations are refused with an error that tells the agent how
  to comply. Analysis uses DuckDB's own parser and **fails closed**: a query too
  odd to certify is refused, not waved through.
- **`groups of at least k`** — k-anonymity. The query is rewritten so any group
  with fewer than k rows is **suppressed from the result** (the clean-room
  standard), and the result carries a warning saying so. Group counts are
  computed *after* row-level security, and when several policied relations are
  involved the strictest k wins.
- **`no joins` / `no joins to a, b`** — the relation may not be *queried
  together* with other relations (deliberately broader than literal JOINs — a
  UNION counts too).

Agents aren't left guessing: `describe_table` on a policied relation returns its
rules (`"policies": ["aggregates only", …]`), so a well-behaved agent writes a
conforming query on the first try. Refusals land in the
[flight recorder](audit.html) like any errored access. The human SQL editor is
unaffected — policies govern the agent surface, like masking and row filters.

## Try it

```sh
uvx datacharter serve examples/ecommerce
# the example's crm table carries: aggregates only · groups of at least 2
```

Ask the agent for "average customer count by region" — works. Ask it to "list
customer emails" — refused, with the policy quoted back.
