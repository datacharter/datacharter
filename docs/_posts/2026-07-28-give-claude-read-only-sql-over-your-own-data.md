---
layout: post
title: "I gave Claude read-only, PII-masked SQL over my own data"
description: "Handing an LLM your database credentials is indefensible. Pasting CSVs into a chat is a joke. Here's the third option: a data contract the agent physically cannot violate."
author: Rishi Mashelkar
---

Large language models are genuinely good at SQL now. Give one your schema and a
question, and it will usually write the query you meant. Which raises an obvious,
uncomfortable question: how do you let it *run* that query?

The options I found were all bad.

**Option one: hand the model database credentials.** Now an autocomplete engine
holds write access to your production replica, sees every raw email address and
phone number in the result set, and ships them to whatever context window it
lives in. If you have ever sat in a data-governance review, you know how that
conversation ends.

**Option two: paste CSVs into the chat.** Manual, tiny, stale, and you have
exfiltrated the data yourself, one clipboard at a time.

**Option three** did not exist, so I built it.

## What I actually wanted

I wrote down the properties I would need before pointing an agent at real data
with a straight face:

1. **Read-only, guaranteed by the system.** Not "the prompt says please don't
   write." The engine refuses writes, no matter what SQL arrives.
2. **PII masked by default.** The model should see `•••` where the email was,
   unless I explicitly grant that column. Masking should survive joins, aliases,
   and `SELECT *`.
3. **Scoped rows and columns.** Not just "which tables": which columns of which
   tables, and which *rows*.
4. **Local.** My data does not leave my machine to be governed.
5. **Provable.** I want to *see* exactly what the agent sees, not trust a
   settings page.

The interesting realization was that most data teams already write the artifact
that could enforce all of this. It's called a data contract: a small YAML file
declaring sources, tables, and which fields are sensitive. It just sits in a
repo, describing data instead of protecting it.

## The contract becomes the enforcement point

DataCharter is a local data explorer built around that idea. You declare your
sources in a `charter.yaml`, and the file stops being documentation:

```yaml
sources:
  crm:
    type: postgres
    tables:
      customers:
        pii: [email, phone]     # masked for agents by default

agent_access:
  crm:
    customers:
      email: deny               # not one column more

row_filters:
  orders: "region = 'US'"       # the rows an agent may see
```

Under the hood, an embedded DuckDB engine federates everything the charter
declares: local CSV and Parquet files, SQLite, Postgres, a warehouse if you have
one. One SQL statement can join a local file to a Postgres table. That part is
almost unreasonable the first time you see it work on a laptop.

On top of that engine sits the governed agent surface. Any model connects
through the [Model Context Protocol](https://modelcontextprotocol.io) and gets
exactly four tools: `list_sources`, `list_tables`, `describe_table`, and
`query`. Every one of them is read-only, and `query` enforces the charter:

- **Writes are rejected before execution.** The SQL parser guard walks the
  query tree; anything that writes, deletes, or touches the filesystem never
  reaches the engine.
- **Masking follows the data, not the column name.** Provenance tracking means
  a PII column comes back masked even through joins, aliases, and `SELECT *`.
- **Predicates can't leak what masking hides.** A masked column can't be used
  in `WHERE`, `JOIN`, `GROUP BY`, or `ORDER BY`, so the model can't
  binary-search its way to a value it isn't allowed to read.
- **Row filters compose with all of it.** The agent sees US orders only, with
  the email column masked, and neither restriction interferes with the other.

## Proof beats promises

My favorite part of the tool is a toggle. Run any query in the UI, flip on
**Agent view**, and the result grid re-renders as the model would receive it.
The rows are there, the aggregates work, and the email column reads `•••`.

That one interaction changed how I think about agent governance. Every other
approach I tried asked me to trust configuration. This one shows me the exact
result set the model gets, column by column. When a colleague asks "but what
does the AI actually see?", the answer is a screenshot, not a paragraph.

## What it looks like in practice

Wire a workspace into Claude Code, Claude Desktop, Cursor, or any MCP client:

```json
{
  "mcpServers": {
    "datacharter": {
      "command": "uvx",
      "args": ["datacharter", "mcp", "/path/to/workspace"]
    }
  }
}
```

Then ask real questions. "What's revenue by region this quarter?" becomes a
governed `query` call; the transcript shows the exact SQL it ran, and one click
opens that SQL in the editor. The model is useful precisely because you can
afford to let it touch real data.

A detail I care about: the chat agent can run on a Claude Code subscription,
on a fully local model via Ollama, or on any OpenAI-compatible endpoint. The
governance layer does not care which brain you plug in. Whichever it is, the
tools are read-only and the PII comes back masked before anything leaves the
engine.

## Try it

DataCharter is open source (Apache-2.0), runs entirely on your machine, and
sends no telemetry. One command starts a workspace on demo data:

```sh
uvx datacharter serve        # or: brew install datacharter/tap/datacharter
```

Point it at your own files and databases with `datacharter init`, flip Agent
view, and see for yourself what "not one column more" looks like.

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[datacharter.dev](https://datacharter.dev)
