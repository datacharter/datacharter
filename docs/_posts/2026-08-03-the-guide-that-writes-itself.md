---
layout: post
title: "The guide that writes itself"
description: "You already wrote the tribal knowledge — one WHERE clause at a time. DataCharter now mines your query history for the habits you repeat and turns them into agent guides, with evidence, fully offline."
author: Rishi Mashelkar
---

A few releases ago I added [guides](agent-context-belongs-in-the-contract.html) —
plain-language context that makes agents dramatically better at answering
questions over your data. The feedback was consistent: *love it… but who's going
to sit down and write them?*

Fair. Nobody documents tribal knowledge. That's what makes it tribal.

But here's the thing I realized while staring at the query history panel: **you
already wrote it.** Every time you typed `WHERE refunded = false`, you wrote a
guide line. You just wrote it in SQL, forty times, instead of English, once.

## Mining the habits

DataCharter 0.16.0 adds:

```sh
$ datacharter suggest
Guide suggestions mined from your query history:

  1. [filter] Queries on `sales` usually filter `refunded = false`
     (14 of 20 recent queries) — treat it as the default filter.
  2. [filter] Queries on `crm.customers` usually filter `tier != 'internal'`
     (9 of 12 recent queries) — treat it as the default filter.
  3. [join] `sales` and `crm.customers` are usually queried together —
     they join naturally.
```

`--apply` writes them into `guides/suggested.md` — a normal guide file you can
edit — and from that moment every agent (chat, Claude Desktop, Cursor, Claude
Code over MCP) inherits your habits. The Guides editor in the browser shows the
same suggestions with an **Add** button.

## The part I'm smug about

There's no model in this loop. DuckDB — the same engine that runs your queries —
also *parses* them: its `json_serialize_sql` function returns a full AST, so
DataCharter walks your WHERE clauses structurally instead of regexing at them.
Deterministic, offline, testable, and the evidence is right there in the
suggestion ("14 of 20 recent queries"). It also dedupes against what your guides
already say, so it never nags about knowledge you've already written down.

And because [evals](measure-your-context-lift.html) exist, you don't have to
take the suggestion's word for it: accept a suggested guide, run
`datacharter eval --compare-guides`, and *measure* whether your own habits made
the agent more accurate. (They will. You filtered those refunds for a reason.)

## The loop, closed

This completes a loop I've been circling for two weeks: the contract governs
what an agent may touch, guides make it smart, evals prove the guides work, the
flight recorder proves what happened, canaries alarm if protection ever fails —
and now the guides bootstrap themselves from the way you already work.

Tribal knowledge, extracted from the tribe's actual behavior. With receipts.

```sh
uvx datacharter suggest    # or: brew install datacharter/tap/datacharter
```

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[datacharter.dev](https://datacharter.dev)
