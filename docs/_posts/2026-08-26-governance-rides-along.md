---
layout: post
title: "Governance rides along"
description: "DuckLabs is joining AWS and the Duck Stack is about to scale. DataCharter now speaks DuckLake — point it at your lakehouse catalog and its tables arrive governed: masked, read-only, contract-checked."
author: Rishi Mashelkar
---

I woke up to the news that DuckLabs is joining AWS. If you've been building on
DuckDB these last few years like I have, it's worth sitting with for a second: the
little in-process database that could is about to reach a whole new scale of
people.

The part I keep coming back to is right there in the announcement — DuckDB stays
MIT, the DuckDB Foundation keeps stewardship, and the open-source pieces stay free
and open. The foundation isn't moving. It just got a much bigger megaphone.

I build DataCharter, a small contract-governance layer that sits on top of DuckDB,
so of course I've been thinking about what this means for those of us building
*around* the Duck Stack. Honestly? It reads to me like a rising tide. More DuckDB,
in more places, is good for everyone building near it.

And it sharpens something I already believed. As the storage layer scales and
consolidates, a governance layer that answers to *your data* — not to any one cloud
— gets more useful, not less. The point of a contract is that it travels: the same
masking, the same read-only guarantee, the same declared PII, whether the data is a
CSV on your laptop, a MotherDuck database, or a lakehouse on someone's object store.

## Which brings me to DuckLake

[DuckLake](https://ducklake.select) is a big part of this story — a lakehouse
format that keeps table metadata in a plain SQL database and the data as Parquet
files. It's exactly the kind of thing that gets a lot more common when the whole
stack gets a megaphone. So this morning I added a DuckLake connector to
DataCharter. It felt like the right way to celebrate.

Point a source at your catalog, and its tables show up on the governed surface like
any other:

```yaml
sources:
  lake:
    type: ducklake
    connection:
      metadata: "postgres:dbname=catalog host=${PG_HOST} user=${PG_USER} password=${PG_PASSWORD}"
      data_path: s3://my-bucket/lake
    credentials:
      key_id: ${AWS_ACCESS_KEY_ID}
      secret: ${AWS_SECRET_ACCESS_KEY}
      region: us-east-1
    tables: [customers, orders]
    pii:
      customers: [email]
```

The metadata catalog can be a local DuckDB file or a Postgres / SQLite / MySQL
database; the data can sit on your disk or in object storage. Either way the
catalog is attached **read-only**, and the columns you declare as PII come back
masked to an AI agent — the same governance every other source gets. Nothing about
the lakehouse changes what a contract means. That's the whole idea: the governance
rides along with the data.

I verified it end-to-end against the real `ducklake` extension — a governed query
and PII masking over a live catalog, not a mock — because a governance feature you
can't trust is worse than no feature at all.

## Try it

```sh
uvx datacharter serve   # or: brew install datacharter/tap/datacharter
```

Congrats to the DuckLabs team — this is well earned. If you're building on the Duck
Stack too, I'd genuinely love to hear what you're making, and whether governance
that travels with your data is something you've been missing.

Code and docs: [github.com/datacharter/datacharter](https://github.com/datacharter/datacharter) ·
[Sources](https://datacharter.dev/sources.html) · [datacharter.dev](https://datacharter.dev)
