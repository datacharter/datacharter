---
title: Guides — teach every agent your data's quirks
description: Markdown notes in guides/ reach every agent — chat, Claude Code, and MCP clients. Write them by hand, or let datacharter suggest mine them from your query history. Measure their lift with evals.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

Guides are the things you'd tell a new analyst on their first day: "revenue is
net of refunds", "exclude accounts with region = 'ZZ'", "order_date is when it
was placed, created_at is a system timestamp." Agents need exactly the same
briefing — and with DataCharter, you write it once and every agent gets it.

## Where guides live

Plain markdown files in your workspace's `guides/` directory:

```
guides/
  overview.md      # created by `datacharter init` with a commented template
  analytics.md     # yours — any *.md file here is a guide
```

They are ordinary files: version them with the contract, review edits in PRs,
and edit them in the app's **Guides** panel or any editor. Per-table notes can
also live in the contract itself, as a source's
[`context:`](charter-yaml.html#context) map — those surface in
`describe_table`, right where an agent is looking at that table.

## Who reads them

Every agent surface, automatically:

- the **built-in chat** and **Claude Code** mode get guides in their system
  context;
- **MCP clients** (Claude Desktop, Cursor, Cline, …) receive them in the
  protocol's `initialize` `instructions` field — no client configuration;
- comment-only or empty guide files are skipped, so the `init` template is
  inert until you write something real.

## Let the guide write itself

```sh
datacharter suggest            # propose guide lines from your query history
datacharter suggest --apply    # append accepted lines to your guides
```

`suggest` mines the workspace's local query history for habits you repeat —
a filter you always apply, a join you always use — and turns each into a
proposed guide line **with the evidence attached**. It runs offline; no model
is involved. It needs some accumulated history to fire, and it skips habits
your guides already cover — a quiet run means you're covered, not broken.
You review every line; nothing ships without you.

## Prove the guides earn their keep

```sh
datacharter eval --compare-guides
#   100% passed  (guides off: 40%  →  lift: +60%)
```

[Evals](evals.html) can run your whole suite with guides on and off and report
the lift — the difference your written context makes to agent accuracy, on
your data, in one number.

## One caution

Guides are *sent to agents*, so treat them like the contract: no secrets, no
real customer data in examples. `datacharter scan` checks guide files for
literal PII and warns before it ships (add `--strict` to fail CI on it).

Next: [Evals — measure agent accuracy →](evals.html)
