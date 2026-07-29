---
title: Agent modes
description: Run on your Claude Code subscription, bring your own endpoint, run fully local, or skip the agent entirely.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

DataCharter has an optional natural-language agent that turns a plain-language
question into SQL against your sources. It is genuinely optional.

## The product is fully usable without any LLM

The engine, the source tree, the SQL editor with catalog autocomplete, the
results grid, charts, the profiling panel, the EXPLAIN viewer, exports, and
drag-and-drop file querying all work with no model configured and no network
access. The agent adds a chat panel on top; nothing else depends on it.

There is no bundled or fine-tuned model. The agent is grounded: it inspects your
schema through tools, scopes to your contract, and retries on SQL errors, which
is the regime where existing models already do text-to-SQL well.

## Mode 1: bring your own endpoint

Point the agent at any OpenAI-compatible `/chat/completions` endpoint (a hosted
API, a self-hosted server such as vLLM, or a local runtime that speaks the same
protocol). Set the endpoint and key in the environment, then serve:

```sh
export OPENAI_BASE_URL=https://api.example.com/v1   # any OpenAI-compatible API
export OPENAI_API_KEY=...
datacharter serve
```

- `OPENAI_BASE_URL` defaults to `https://api.openai.com/v1` if unset.
- `DATACHARTER_MODEL` selects the model (default `gpt-4o-mini`).
- The client is a dependency-free `httpx` wrapper; there is no vendor SDK.

## Mode 2: fully local with `--local`

Run the agent against a local [Ollama](https://ollama.com) instance. No API key,
no data leaves your machine:

```sh
datacharter serve --local              # uses qwen3:8b by default
datacharter serve --local --model ...  # choose another Ollama model
```

- `--local` targets Ollama at `http://127.0.0.1:11434/v1`.
- The default model is `qwen3:8b`; override with `--model`.
- DataCharter never auto-installs third-party software. If Ollama is not
  reachable, it prints an install hint (and the `ollama pull` command for your
  chosen model) and serves without the agent. The UI still works; the chat is
  simply disabled.

## Mode 3: your Claude Code subscription

If you have [Claude Code](https://claude.com/claude-code) installed and are signed
in to a Claude Pro or Max plan, the agent can run on that subscription — no API
key and no per-token billing. In the chat panel, click **Connect Claude Code**
(shown next to *Connect an LLM*) and start asking questions.

- Requires the `claude` CLI on your `PATH` and an active Claude subscription.
- DataCharter drives Claude Code headlessly, one turn per question. Claude reaches
  your data **only** through the same four read-only, access-governed tools below —
  never your raw files or connections.
- The connection is **fail-closed**: before enabling it, DataCharter verifies that
  the tool sandbox exposes nothing beyond those governed tools, and refuses to
  connect otherwise.
- This is **not** a no-egress mode. Because Claude Code runs against Anthropic's
  models, your questions and the (PII-masked) tool results are sent to Anthropic
  under your Claude subscription. Use `--local` (Mode 2) if no data may leave your
  machine.

## Guides: tell the agent what you'd tell a colleague

Schema alone doesn't say that revenue means *net of refunds* or that QA
accounts must be excluded. Put that in `guides/*.md` (and per-table
[`context:`](charter-yaml.html#context-and-guides-agent-context)) and every
agent — the built-in chat, Claude Code, and any MCP client — receives it before
writing a query. See the end-to-end
[example workspace](https://github.com/datacharter/datacharter/tree/main/examples/ecommerce)
for a working guide.

## How the agent works

The agent runs a short tool loop over a small set of **read-only** tools:

| Tool | What it does |
| --- | --- |
| `list_sources` | List configured sources and their types. |
| `list_tables` | List queryable tables with their relation names. |
| `describe_table` | Show columns and types for one relation. |
| `query` | Run a read-only SQL query and return rows. |

- **Access is governed and PII-safe.** By default the agent sees masked values
  (`•••`) for any column that is declared PII in `charter.yaml` *or* auto-detected
  as PII when you serve. Override access at the source, table, or column level —
  from the data explorer's left panel or via the contract's
  [`agent_access`](charter-yaml.html#agent_access) block — to unmask a
  non-sensitive column or hide one that isn't PII. Flip **Agent view** on any
  result to see exactly what the agent receives. The same governance applies over
  [MCP](mcp.html) and to Claude Code. Masking is enforced, not cosmetic: a masked
  column may be selected (values return as `•••`) but cannot be used to filter,
  join, group, or order results, so its values can't be inferred by predicate.
  The human SQL editor is unaffected.
- **Row-level security (optional).** Declare `row_filters` in `charter.yaml` to
  limit the agent to specific rows per table (e.g. `orders: "region = 'US'"`);
  its queries are rewritten to honor the filter, fail-closed. See the
  [charter.yaml reference](charter-yaml.html#row_filters).
- **Read-only is enforced in the engine**, not just the prompt: a statement
  allowlist rejects anything but queries (the only write path is `local.*` DDL
  for snapshots). The agent cannot modify your data.
- **Charts inline.** The agent can emit a Vega-Lite spec that renders directly in
  the results panel.
- **Reproducible answers.** Each query the agent runs appears in the transcript as
  the exact governed SQL, with one click to open it in the editor and run it
  yourself.
- **Streaming.** Answers stream to the chat panel over Server-Sent Events
  (`/api/agent/ask`). `/api/agent/available` reports whether an endpoint is
  configured and which model is in use.

See the [quick-start guide](quickstart.html) to get a workspace running first,
then turn the agent on with either mode above.
