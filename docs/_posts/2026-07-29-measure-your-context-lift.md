---
layout: post
title: "Measure your context lift"
description: "A week ago I argued that agent context belongs in the contract. Fair question back: how do you know it helps? DataCharter 0.12.0 answers it — eval suites that score the agent on your data and show exactly how much your guides moved the needle."
author: Rishi Mashelkar
---

Last week I made a claim: [agent context belongs in the
contract](https://datacharter.dev/blog/agent-context-belongs-in-the-contract/) — put the tribal
knowledge in `guides/*.md` and every agent gets smarter about your data. A
reader asked the obvious thing back: *how do you know it actually helps?*

Good question. "Trust me, context helps" is exactly the kind of hand-wave I'd be
suspicious of. So DataCharter 0.12.0 ships the other half: **evals you run on
your own data, that tell you the number.**

## Write the questions you actually ask

An eval suite is just a file — `evals/analytics.yaml` — listing the questions
your team asks the data and what a correct answer has to look like:

```yaml
version: 1
cases:
  - question: "What is our net revenue?"
    expect:
      - { type: sql_contains, value: "refunded" }   # net = excludes refunds
      - { type: sql_excludes, value: "email" }        # never reaches for PII
```

The assertions are the interesting design choice. An agent names its own result
columns unpredictably, so binding a check to a column is fragile. Instead
assertions bind to what's *stable*: the answer text, the **SQL the agent ran**,
or the last query's scalar. And once you can assert on the SQL, you can check
something subtle for free — did the agent *follow the guide?* "Net revenue
excludes refunds" becomes `sql_contains: refunded`. If the model forgot, the
eval fails, in red, in CI.

## The number that matters

Here's the headline. Run it with one flag:

```sh
datacharter eval --compare-guides
```

DataCharter runs the whole suite twice — once with your guides in the agent's
context, once with them stripped — and prints the delta:

```
  ✓ What is our net revenue?
      guides on: ✓   guides off: ✗
  ✓ How many customers, excluding test accounts?
      guides on: ✓   guides off: ✗

  100% passed  (guides off: 0%  →  lift: +100%)
```

That `+100%` is *your* context lift, on *your* data, computed on your laptop —
not a benchmark number from someone else's warehouse. Add `--threshold 0.8` and
it exits non-zero below 80%, so a regression in agent accuracy blocks the pull
request instead of surfacing in production. Runs persist to a local ledger, so
`datacharter eval --history` shows the trend and tells you exactly which case
regressed since last time.

## And you never have to leave the browser

`datacharter serve` now has an **Evals** panel — write cases, hit Run, watch the
scorecard, the guide-lift bar, and the trend chart fill in. Next to it, a
**Guides** editor so you can write the context and immediately measure whether it
helped. Both edit your workspace files directly, and both are locked to a
loopback server — this is your machine, your data, your call.

## Try it

The repo ships a worked [example
workspace](https://github.com/datacharter/datacharter/tree/main/examples/ecommerce)
with a suite whose pass/fail visibly depends on the guide:

```sh
uvx datacharter eval examples/ecommerce --compare-guides
```

Context makes agents accurate. Evals make "accurate" a number you can watch. Put
both in the contract, and your data's tribal knowledge finally has a home that
argues its own worth.

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[Agent evals](https://datacharter.dev/evals.html) · [datacharter.dev](https://datacharter.dev)
