---
layout: post
title: "Agent context belongs in the contract"
description: "MotherDuck just showed that prose context is the biggest lever for agent SQL accuracy. Here's the local, contract-governed take: guides that live in your repo and ship through the governed surface — in DataCharter 0.11.0, out today."
author: Rishi Mashelkar
---

[MotherDuck launched Guides](https://motherduck.com/blog/) this week: markdown
context for analytics agents, stored in the warehouse. In their benchmarking on
419 DABStep questions, guides improved agent accuracy by 72 percentage points
and cut cost per run by 55%.

Those numbers deserve attention, because they confirm something that anyone who
has watched an agent write SQL already suspects: **the model's biggest handicap
isn't SQL skill, it's missing tribal knowledge.** The schema says `amount` is a
`DECIMAL`. It does not say that revenue means net of refunds, that QA accounts
have `tier = 'internal'`, or that `created_at` is a system timestamp nobody
should group by. A colleague would tell you all of that in two minutes. The
agent gets none of it.

MotherDuck's answer is to store that knowledge in the warehouse. It's a good
answer for warehouse-native teams. But it made me want to argue for a slightly
different home.

## Context is a contract concern

DataCharter is built on one idea: the data contract you already write — sources,
tables, PII — should be *enforced*, not just documented. Masking, row-level
security, and read-only access all flow from `charter.yaml`.

Tribal knowledge belongs in the same place, because it has the same properties:

- **It should be versioned.** "Revenue means net of refunds" is a definition
  someone decided. Definitions change; you want the diff and the blame.
- **It should be reviewed.** A guide edit changes what every agent will believe
  about your data. That is exactly what pull requests are for.
- **It should travel.** A workspace you can `git clone && datacharter serve`
  should arrive knowing its own quirks, on any machine, with no cloud attached.

So as of **DataCharter 0.11.0** (out today), context lives with the contract:

```
my-workspace/
  charter.yaml
  guides/
    analytics.md      # "net revenue excludes refunded orders…"
  data/
```

Free-form markdown in `guides/*.md`, plus per-table notes in the charter
itself:

```yaml
sources:
  crm:
    type: postgres
    tables: [customers]
    context:
      customers: "One row per customer; tier = 'internal' marks QA accounts — exclude them."
```

## Served through the governed surface

The interesting part is the delivery. DataCharter exposes exactly four
read-only, PII-masked tools to agents, and guides ride the surfaces that
already exist:

- The **built-in chat agent** gets guides in its system prompt.
- **Claude Code** gets them appended to its system prompt by the driver.
- **Every MCP client** — Claude Desktop, Cursor, Cline, Gemini CLI — receives
  them through the Model Context Protocol's `initialize` `instructions` field,
  which clients inject into model context automatically.
- `describe_table` returns a table's declared context right next to its schema
  and masked columns.

No new tools, no separate context store, no sync job. And because guides pass
through the same surface that masks PII and enforces row filters, the agent
that knows your revenue definition still can't see one column more than the
contract grants.

## Try it in two minutes

The repo ships an [end-to-end example workspace](https://github.com/datacharter/datacharter/tree/main/examples/ecommerce)
with all of it wired together: PII masking, agent access, row filters, guides,
data tests, and a metric. Point any MCP client at it and ask "what's revenue by
region?" — the guide steers the model to net revenue and away from the QA
accounts, and the masking makes sure the identities never leave your machine.

```sh
uvx datacharter serve examples/ecommerce   # or: brew install datacharter/tap/datacharter
```

Context makes agents accurate. Contracts make them safe. They belong in the
same file tree.

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[datacharter.dev](https://datacharter.dev)
