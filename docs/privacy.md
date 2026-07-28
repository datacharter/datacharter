---
title: Privacy Policy
description: DataCharter runs locally and does not collect your data.
---

# Privacy Policy

_Last updated: 2026-07-28_

DataCharter is a local-first, open-source (Apache-2.0) tool. It runs entirely on
your own machine. This policy explains what happens to your data — the short
version is: nothing leaves your control.

## Data collection

DataCharter does **not** collect, transmit, or store your data, queries, schemas,
credentials, or usage. There is no telemetry, no analytics, no crash reporting, no
account system, and no server operated by the DataCharter project.

## How your data is used

- DataCharter reads only the data sources you declare in your `charter.yaml`, and
  only to answer the queries you — or an AI agent you connect — run.
- Your data and query results stay on your machine, except when sent to a data
  source you configured (e.g. your own database) or to a third-party model
  provider you explicitly enable (see below).
- Credentials are read from your local environment / `.env`, are never logged, and
  are scrubbed from error messages.

## Third-party model providers

If you enable DataCharter's AI-agent features with a third-party LLM (for example
via `OPENAI_BASE_URL`, a local model, or a Claude Code subscription), the prompts
and query results DataCharter sends to that model are governed by **that
provider's** privacy policy. DataCharter's PII masking limits what leaves your
machine, and you choose which provider (if any) to use.

## Data storage and retention

DataCharter stores only what you create locally — your `charter.yaml`, any local
snapshots, and query history if you use it. These live on your machine and are
deleted when you delete them. The project retains nothing.

## Third-party sharing

The DataCharter project neither receives nor shares any of your data. There is
nothing for us to share.

## Contact

Questions or concerns: open an issue at
<https://github.com/datacharter/datacharter/issues>.
