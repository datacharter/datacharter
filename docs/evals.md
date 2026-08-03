---
title: Agent evals
description: Measure how well agents answer over your data — and how much your guides help.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

[Guides](charter-yaml.html#context-and-guides-agent-context) claim that context
makes agents better. **Evals prove it — on your data, locally.** Write the
questions you actually ask, assert what a correct answer must contain, and score
the agent against them. With one flag you get the number that matters: how much
your guides moved accuracy.

## A suite is `evals/*.yaml`

```yaml
version: 1
cases:
  - question: "What is our net revenue?"
    expect:
      - { type: sql_contains, value: "refunded" }   # net = excludes refunds
      - { type: sql_excludes, value: "email" }        # never reaches for PII
    expected_answer: "Net revenue is about $512."     # optional → enables the judge
```

Assertions bind to stable surfaces — the agent's **answer**, the **SQL it ran**,
or the **last query's scalar** — never to the columns the model happens to name.
That also makes `sql_contains` a direct check of whether the agent *followed a
guide*.

| type | fields | passes when |
|---|---|---|
| `answer_contains` | `value` | the value appears in the final answer |
| `answer_matches` | `pattern` | the regex matches the final answer |
| `sql_contains` | `value` | the value appears in some SQL the agent ran |
| `sql_excludes` | `value` | the value appears in none of the SQL |
| `result_scalar` | `equals`, `tolerance?` | the last query returned one cell within tolerance |

A case passes when every assertion passes; the suite score is the fraction of
cases passed. With `--judge`, any case that sets `expected_answer` is *also*
graded by an LLM (does the agent's answer match the reference?), folded into the
case result alongside the deterministic assertions.

## Run it

```sh
datacharter eval                       # score the current workspace
datacharter eval examples/ecommerce    # score a specific workspace
datacharter eval --compare-guides      # ← the headline: guides on vs. off + lift
datacharter eval --threshold 0.8       # exit non-zero below 80% (for CI)
datacharter eval --history             # pass-rate trend + what regressed
datacharter eval --samples 3           # run each case 3×; pass = majority
datacharter eval --judge               # also LLM-grade freeform answers vs expected_answer
```

`--compare-guides` runs the whole suite twice — once with your guides in the
agent's context, once with them stripped — and prints the delta:

```
  100% passed  (guides off: 40%  →  lift: +60%)
```

Evals run your real agent, so they cost tokens and are non-deterministic. Use
`--samples` to average, and `--local` to run against a local model for free.

**An agent endpoint is required.** Set `OPENAI_BASE_URL` / `OPENAI_API_KEY`
(any OpenAI-compatible endpoint), or pass `--local` to use Ollama. With
nothing configured, `datacharter eval` refuses with a hint — a suite can't
score answers no agent produced. `--judge` uses the same endpoint to grade
freeform answers.

## In CI

Drop it into the [DataCharter Action](https://github.com/marketplace/actions/datacharter-data-checks)
alongside `test` and `drift`, with a threshold, so a regression in agent
accuracy blocks the PR rather than surfacing in production.

## In the browser

`datacharter serve` has an **Evals** panel — author cases, hit Run, and watch
the scorecard, the guide-lift bar, and the trend chart. The neighbouring
**Guides** editor lets you write `guides/*.md` and per-table context without
leaving the app. Editing is only enabled on a loopback server.

Next: [The flight recorder and canaries →](audit.html)
