# DataCharter

> Query all your data locally. Hand agents exactly the columns you choose.

A local SQL workspace over files and databases, federated by DuckDB and
governed by `charter.yaml`. Agents get read-only, PII-masked access to what
the contract grants. Apache-2.0. No paid edition.

<!-- mcp-name: io.github.datacharter/datacharter -->

[![PyPI](https://img.shields.io/pypi/v/datacharter)](https://pypi.org/project/datacharter/)
[![Python](https://img.shields.io/pypi/pyversions/datacharter)](https://pypi.org/project/datacharter/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue)](LICENSE)

**[datacharter.dev](https://datacharter.dev)** ·
[Docs](https://datacharter.dev/quickstart.html) ·
[Desktop](https://datacharter.dev/desktop.html) ·
[GovBench](https://datacharter.dev/govbench.html) ·
[Deploy](https://datacharter.dev/deploy.html)

Two ways in. Same kernel.

## Laptop

Drop a file. Query it. Chart it. An agent sees `•••` where PII lives.

```sh
uvx datacharter serve          # demo workspace, http://127.0.0.1:8321
# or: datacharter init --from && datacharter serve
# or: datacharter init --template life && datacharter serve --local
```

No terminal: [desktop app (beta)](https://github.com/datacharter/datacharter/releases/latest).
macOS (Apple Silicon) or Windows. Unsigned until Apple secrets exist.

```sh
brew install datacharter/tap/datacharter   # macOS
pip install datacharter                    # Python 3.11+
```

The workspace is a directory: `charter.yaml`, `queries/`, `guides/`. Commit it.
Secrets stay out. Optional agent: SpaceXAI, Claude Code, Ollama (`--local`),
or any OpenAI-compatible endpoint.

## Company

The same binary, on a shared MCP endpoint. Identities live in git, not on
our servers. No rows leave your infrastructure.

```sh
datacharter mcp --http --host 0.0.0.0   # OAuth env required off loopback
helm install datacharter ./chart \
  --set oauth.issuer=... --set oauth.audience=... --set oauth.jwksUri=...
datacharter govbench --json             # cite corpus govbench-v1
```

- MCP Streamable HTTP (`POST /mcp`) with optional [OAuth 2.1](https://datacharter.dev/mcp.html)
- `principals:` and `grants:` in `charter.yaml` (default-deny on HTTP)
- [Helm chart](https://datacharter.dev/deploy.html) and OCI image
- Hash-chained [audit](https://datacharter.dev/audit.html) plus SIEM JSON/OTLP
- [GovBench](https://datacharter.dev/govbench.html): frozen 28-attack corpus, grade A-F

Wrap someone else's MCP server: `datacharter mcp --guard "npx -y some-mcp-server"`.

## What the contract enforces

PII default-deny, row filters, plain-English policies (`aggregates only`),
canaries, a flight recorder, `datacharter redteam`, `access diff` on PRs.
CLI reference: [docs/cli.md](docs/cli.md). Security: [docs/security.md](docs/security.md).

**Status:** pre-release. V1 in development.

## Privacy

Runs on your machine or in your cluster. No telemetry. No DataCharter-operated
data plane. [Privacy Policy](https://datacharter.dev/privacy).

## License

[Apache-2.0](LICENSE)
