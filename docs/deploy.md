---
layout: default
title: Deploy with Helm
description: Run DataCharter MCP HTTP in a cluster. OAuth required, hash-chain audit on disk, optional SIEM export.
---

The cluster artifact is MCP Streamable HTTP, not the local UI. Bind
`0.0.0.0` only with OAuth. Stdio MCP stays the laptop default; its image is
the repo-root `Dockerfile`.

## OCI image

Build from this commit:

```sh
docker build -f packaging/oci/Dockerfile -t datacharter:dev .
```

The image runs `datacharter mcp --http --host 0.0.0.0 --port 8765 /workspace`
as uid 10001. Mount a workspace at `/workspace`. Set all three OAuth env
vars or the process refuses to bind.

```sh
docker run --rm -p 8765:8765 \
  -e DATACHARTER_OAUTH_ISSUER=https://auth.example.com \
  -e DATACHARTER_OAUTH_AUDIENCE=https://datacharter.example.com/mcp \
  -e DATACHARTER_OAUTH_JWKS_URI=https://auth.example.com/.well-known/jwks.json \
  -v "$PWD:/workspace" datacharter:dev
```

Kubelet probes: `GET /health` (liveness) and `GET /ready` (toolbox is up).
They take no token and skip the Host/Origin guards.

Registry push is not part of CI yet. Tag and push to your registry, then
point the chart at that repository.

## Helm chart

```sh
helm lint chart \
  --set oauth.issuer=https://auth.example.com \
  --set oauth.audience=https://datacharter.example.com/mcp \
  --set oauth.jwksUri=https://auth.example.com/.well-known/jwks.json

helm install datacharter ./chart \
  --set image.repository=datacharter \
  --set image.tag=dev \
  --set oauth.issuer=https://auth.example.com \
  --set oauth.audience=https://datacharter.example.com/mcp \
  --set oauth.jwksUri=https://auth.example.com/.well-known/jwks.json \
  --set-file charter=charter.yaml
```

Install fails if any OAuth field is empty. That is the same rule as
`datacharter mcp --http --host 0.0.0.0`.

The chart mounts `charter.yaml` from a ConfigMap, optional credentials from
an existing Secret (`credentialsSecret`, keys match `${ENV}` refs), `/tmp`
and `$HOME` as emptyDir (read-only root filesystem), and probes `/health`
and `/ready`. Pod uid is 10001.

SIEM copy of the audit chain:

```yaml
extraEnv:
  - name: DATACHARTER_AUDIT
    value: json
  - name: DATACHARTER_OTLP_ENDPOINT
    value: http://otel-collector:4318
```

The hash chain still writes under `/workspace/.datacharter/flight` in the
pod. See [Audit](audit.html#siem-json-and-otlp).

## What this is not

`datacharter serve` on loopback is the UI. Do not Helm that. The catalog
stdio image (`docker build -t datacharter-mcp .`) is for Docker Desktop MCP
Toolkit, not for a Service.

Next: [MCP server](mcp.html)
