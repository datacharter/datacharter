---
layout: post
title: "Tripwires for AI data leaks"
description: "Security folks have loved honeytokens for decades: any touch is by definition suspicious. DataCharter 0.15.0 plants them for AI agents — masked canaries that can only surface if your protection layer actually failed."
author: Rishi Mashelkar
---

Security teams have a trick they've loved for decades: the honeytoken. Plant a
fake credential, a fake database row, a fake AWS key — something no legitimate
process would ever touch — and wire it to an alarm. The beauty is the signal
quality: there are no false positives, because *any* interaction with the bait
is, by definition, wrong.

Yesterday I shipped a [flight recorder](the-black-box-flight-recorder-for-ai-data-access.html)
that proves what your AI agents did. Today's release answers a nastier
question: **how would you know the moment your protections stop working?**

## Canaries, but masked

DataCharter 0.15.0 adds canary tripwires with one line in your contract:

```yaml
canary: on
```

That plants `local.canaries` — a small table of synthetic PII whose values embed
unique tokens like `canary-8f3a2c1d@tripwire.invalid`. Here's the twist that
makes it interesting: the table is **masked by the exact same machinery that
protects your real data**. An agent that queries it sees `•••`, the same as your
customers' emails.

Follow that to its conclusion. The canaries are synthetic, so they exist nowhere
else. They're masked, so a working governance layer never lets them out. Which
means a canary token appearing in agent output isn't *suspicious* — it's
**proof**: masking or the query guard failed, right there, on that query. The
classic honeytoken property, aimed at a new target. Not "did someone touch the
bait" but "did the safety net tear."

## When the wire trips

The alarm lands as an entry in the flight recorder's hash chain — so the
evidence of the failure is itself tamper-evident — and lights up a red banner in
the Audit panel. And you choose the response posture:

```yaml
canary: on              # block: withhold any response carrying a canary
canary: { mode: log }   # log: let it through, alarm loudly
```

Block mode is my favorite part. Since there is no legitimate reason for a canary
to surface, withholding the response costs nothing — the tripwire doesn't just
report the leak, it stops it.

Trust, but verify — including the tripwire itself:

```sh
$ datacharter canary drill
Drill OK: token detected and alarm recorded in the audit chain.
```

The drill pushes a synthetic hit through the real detection-and-alarm path, so
you're never wondering whether the wire is actually connected.

## The shape this is all taking

Each piece of DataCharter now covers a different tense: the contract governs
what an agent *may* do, guides make it *smart* about your data, evals *measure*
how well that works, the flight recorder proves what *did* happen — and
canaries alarm the instant the whole apparatus *fails*. Defense in depth, on
your laptop, in a YAML file.

```sh
uvx datacharter serve   # or: brew install datacharter/tap/datacharter
```

It's opt-in — add `canary: on` to a workspace and run the drill. And if you can
get a canary out *without* tripping the alarm, that's a bug report I'll drop
everything for.

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[Audit & canaries](https://datacharter.dev/audit.html) · [datacharter.dev](https://datacharter.dev)
