---
layout: post
title: "Clean-room math for your laptop"
description: "Google's clean room won't return a row unless 50 users stand behind it. DataCharter 0.17.0 brings that class of control home: plain-English policies — aggregates only, groups of at least k, no joins to X — enforced by query analysis."
author: Rishi Mashelkar
---

There's a class of privacy control that, until now, basically lived inside
enterprise clean rooms. Google's Ads Data Hub won't return a row of results
unless at least 50 users are aggregated behind it. LiveRamp ships "aggregation
threshold" rules. The idea is simple and strong: don't just hide the sensitive
columns — make it *mathematically awkward* to learn anything about an
individual at all.

DataCharter 0.17.0 brings that home. In your charter, written the way you'd say
it out loud:

```yaml
policies:
  crm.customers:
    - aggregates only
    - groups of at least 10
    - no joins to payments
```

No model interprets those sentences. They're a tiny controlled grammar,
compiled deterministically — write something the grammar doesn't know and the
charter refuses to load. Plain English going in; exact math coming out.

## What the agent experiences

Ask for a distribution and everything's normal:

```
SELECT tier, count(*) FROM crm.customers GROUP BY tier   ✓
```

…except any tier with fewer than 10 customers simply isn't in the result, and
the response says so: *"k-anonymity: groups smaller than 10 were suppressed."*
That's the clean-room move — suppress the cohort, don't fail the query.

Ask for rows, and:

```
SELECT email FROM crm.customers
→ Error: policy — `crm.customers` allows aggregates only. Write one plain
  SELECT with aggregate functions (and GROUP BY if needed).
```

The agent isn't left guessing, either — `describe_table` returns the rules
right next to the schema, so a well-behaved model writes a conforming query on
the first try. And every refusal lands in the
[flight recorder](the-black-box-flight-recorder-for-ai-data-access.html),
because a policy that blocks silently is a policy you can't prove.

## The paranoid parts, on purpose

Enforcement uses DuckDB's own parser to certify query shape, and it **fails
closed**: DISTINCT is row egress, so it's refused. CTEs and UNIONs are too
shapeshifty to certify, so they're refused with instructions to simplify. "No
joins to payments" actually means *may not appear in the same query as
payments* — deliberately broader than a literal JOIN, because re-identification
doesn't care about your join syntax. Group counts are computed *after*
row-level security. When two policied tables meet, the strictest k wins.

Could a sufficiently determined analyst with unfettered SQL still difference
two aggregates and corner an individual? Over enough queries, differencing
attacks are real — that's what differential-privacy noise is for, and it's on
the roadmap. What ships today is the same bar the industry's clean rooms set,
running on your laptop, versioned in git, applied to every agent surface at
once.

```sh
uvx datacharter serve examples/ecommerce
# the example's crm table ships with: aggregates only · groups of at least 2
```

One YAML block between your agents and your individuals — and receipts when it
does its job.

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[Policies docs](https://datacharter.dev/policies.html) · [datacharter.dev](https://datacharter.dev)
