---
title: Audit — the flight recorder
description: A tamper-evident record of every agent data access, with one-command verification and evidence export.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

Governance without evidence is a promise. The flight recorder turns it into a
record: **every agent data access is logged, hash-chained, and verifiable** —
who asked, through which client, what SQL ran, which columns were masked, and a
fingerprint of exactly what the agent saw. On by default; a black box you switch
*off* (`audit: off` in `charter.yaml`), not on.

## What gets recorded

Two entry types, appended to `.datacharter/flight/*.jsonl`:

- **Session** — written when an agent surface connects: the surface (`chat`,
  `mcp`, `claude-code`), the OS user, and the system identity (the MCP client's
  own `clientInfo` — Claude Desktop, Cursor, Cline — or the chat model). That's
  the *dual attribution* auditors ask for: the human **and** the AI system.
- **Access** — one per tool call: the SQL or relation, relations and columns
  touched, **which columns came back masked**, row count, any error, and a
  SHA-256 of the exact (masked) result the agent saw.

The log stores metadata and hashes — **never raw rows** — so the audit trail
can't become a second copy of your sensitive data.

## Tamper-evidence

Each entry carries the previous entry's hash and its own SHA-256 over the
canonicalized content. Edit any line, delete any line, reorder anything — the
chain breaks, and verification names the exact entry:

```sh
$ datacharter audit verify
5412 entries verified (head 3f9c21ab04d1) ✓

$ datacharter audit verify        # after someone edits history
chain BROKEN at seq 214: entry content does not match its hash
```

## Evidence packs

```sh
datacharter audit                          # recent sessions at a glance
datacharter audit export --since 2026-07-01 --until 2026-10-01
```

The export is a zip an auditor can hold: the window's entries, a verification
statement, the `charter.yaml` that was in force (the policy), and a summary —
sessions, tools, relations touched, masked-column counts. *Everything any agent
saw about your data, provable.*

## In the browser

`datacharter serve` has an **Audit** panel: a session timeline (who connected,
what they asked, every query with its masking) under a live **chain verified ✓**
badge, and an **Export evidence** button that downloads the same self-contained
pack as `datacharter audit export`.

## Canary tripwires

Auditing tells you what happened; canaries tell you the moment protection
*fails*. Enable with one line:

```yaml
canary: on              # block mode — withhold any response carrying a canary
canary: { mode: log }   # or: let it through, alarm loudly
```

DataCharter plants `local.canaries` — synthetic PII whose values embed unique
tokens — and masks it with the same machinery that protects your real data. An
agent that queries it sees `•••`, like everything else. Which means **a canary
token in agent output means masking or the query guard failed on that path** —
canaries are designed so that no governed query can legitimately return one, so
alarms are near-zero false-positive by construction. Alarms land in the hash chain (tamper-evident),
light up the Audit panel, and in block mode the response is withheld.

```sh
datacharter canary            # armed / disabled + how to enable
datacharter canary drill      # deliberately trip the alarm path, end to end
```

## Notes

- Recording is failure-safe: an audit write error never breaks a query.
- Human SQL in the editor is not part of the agent audit chain; it stays in the
  existing query [history](cli.html).
- Concurrent surfaces (serve + mcp on one workspace) serialize through a lock,
  so the chain stays linear.

Next: [Prove an answer — verifiable provenance →](provenance.html)
