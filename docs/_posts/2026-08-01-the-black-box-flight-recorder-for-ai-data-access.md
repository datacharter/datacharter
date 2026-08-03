---
layout: post
title: "The black-box flight recorder for AI data access"
description: "Most teams running AI agents can't answer 'what did it touch?'. DataCharter 0.14.0 ships the missing piece: a tamper-evident audit trail of every agent query — dual-attributed, hash-chained, exportable as evidence."
author: Rishi Mashelkar
---

Here's the pattern that stopped me cold this week: ask a team running AI agents
"what did your agent touch last Tuesday?" and watch the room go quiet. Surveys
of enterprise MCP adoption keep finding the same blocker near the top —
**the missing audit trail**. There's no standard record of which tools an agent
called, with what arguments, and what came back; every incident review starts
from screenshots and vibes.

Airplanes solved this problem decades ago. You don't argue about what happened
on a flight — you pull the black box.

So DataCharter 0.14.0 ships one.

## Every access, on the record

DataCharter already sits at a convenient chokepoint: every agent query — the
built-in chat, Claude Desktop, Cursor, Cline over MCP, Claude Code — flows
through the same four governed tools. As of 0.14.0, each call is recorded:

```json
{"seq": 2, "ts": "2026-08-01T12:00:05Z", "type": "access", "session": "a1b2",
 "tool": "query", "sql": "SELECT email FROM crm.customers",
 "masked_columns": ["email"], "row_count": 50,
 "result_sha256": "9f2c…", "prev": "3e81…", "hash": "c04a…"}
```

Notice what's there — and what isn't. The SQL, the columns that came back
masked, a fingerprint of the exact result the agent saw. **No raw rows.** An
audit log that copies your data is just a second thing to leak; this one stores
metadata and hashes.

Sessions get **dual attribution**, which is the thing compliance folks actually
ask for: the OS user *and* the AI system identity. When an MCP client connects,
it introduces itself — Claude Desktop, Cursor, whoever — and that identity goes
in the record. Who accessed what, when, through which system. Answered.

## The part I like most: it argues back

Each entry carries the previous entry's hash, and its own hash covers its
content. Edit one line of history — one character of one SQL string — and:

```sh
$ datacharter audit verify
chain BROKEN at seq 214: entry content does not match its hash
```

Delete a line? The chain breaks. Reorder? Breaks. The log doesn't ask you to
trust it; it invites you to check.

And when someone upstream asks "what have the agents been doing in there?", one
command produces an evidence pack — the entries, a verification statement, the
contract that was in force, and a summary — as a zip you can hand over:

```sh
datacharter audit export --since 2026-07-01
```

## On by default, off by choice

A black box you have to remember to switch on isn't a black box. Recording is
on by default, failure-safe (an audit write can never break a query), local
like everything else, and `audit: off` in the charter turns it off if you truly
want that. `datacharter serve` grew an **Audit** panel — a session timeline
under a live "chain verified ✓" badge.

It joins what's become a pattern I'm fond of: the contract *grants* access,
guides make the agent *smart* about it, evals *measure* it, and now the flight
recorder *proves* what happened. Governance with receipts.

```sh
uvx datacharter serve   # or: brew install datacharter/tap/datacharter
```

Try it, ask your agent something, then run `datacharter audit` — and if you can
break the chain without `verify` noticing, I very much want to hear from you.

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[Audit docs](https://datacharter.dev/audit.html) · [datacharter.dev](https://datacharter.dev)
