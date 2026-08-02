---
layout: post
title: "Take the tour"
description: "Seven features in a week meant new panels that opened empty for first-time visitors. DataCharter 0.18.0 ships a demo workspace where everything is real — and an 11-step tour that walks you through it."
author: Rishi Mashelkar
---

I shipped seven things in a week — guides, evals, an LLM judge, a flight
recorder, canary tripwires, a desktop app, plain-English policies. Then I opened
DataCharter the way a first-time visitor does, and felt the problem immediately:
the new **Evals**, **Guides**, and **Audit** tabs were *empty*. All that work,
invisible to exactly the person I most wanted to reach.

Empty states are where good products go to die. So 0.18.0 is about the first
five minutes.

## A demo workspace where everything is real

Run `datacharter serve` in a folder with no charter and you now get a workspace
with all of it wired up: a written guide, a runnable eval suite, canary
tripwires armed, a policy on the customers table (`aggregates only` ·
`groups of at least 2`) — and, my favorite part, **a genuine audit chain**.

Not fabricated rows. When that workspace is created, DataCharter actually runs
two agent queries through the real recorder: one allowed aggregate, and one raw
`SELECT email` that the policy **refuses**. So the Audit panel greets you with
`✓ chain verified · 3 entries`, and `datacharter audit verify` genuinely passes,
because the entries are genuine.

The demo data earns its keep too. There are three customers: two `pro`, one
`free`. With `groups of at least 2`, asking an agent for a tier breakdown
returns `pro: 2` — and the single `free` customer is *suppressed*, with the
result saying so. K-anonymity, demonstrated on three rows.

## Eleven steps

The in-app tour used to be five steps about querying. It's now eleven, and the
back half is the governance arc — each step opening the panel it describes:

> the contract is the product → see what an agent sees → teach it your quirks →
> rules in plain English → prove it happened → measure it, don't trust it

## Two bugs that only running it could find

While building this I broke `datacharter serve` on tour workspaces — the seeder
created the local state database with a different encryption key than the server
uses, so it couldn't be reopened. Every unit test passed. Only launching the
thing revealed it.

And a reader-reported one, same family: in the **desktop app**, "Connect Claude
Code" never appeared. A GUI-launched app inherits a minimal `PATH` — no
`~/.local/bin`, no Homebrew — so the `claude` binary was invisible even on
machines that obviously had it. Now detection looks where CLI tools actually
live.

Both are the same lesson, twice in one day: **tests prove the shape, running it
proves it works.** I keep re-learning this, so I'm writing it down where you can
watch me learn it.

```sh
uvx datacharter serve    # then take the tour
```

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[datacharter.dev](https://datacharter.dev)
