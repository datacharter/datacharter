# datacharter MCP server (stdio) — the governed, read-only, PII-masked query
# tools (list_sources, list_tables, describe_table, query, list_metrics,
# query_metric) over the Model Context Protocol.
#
# Self-contained: installs a pinned datacharter on the system PATH and bakes a
# small demo workspace backed by a CSV (a core DuckDB reader — no extension
# downloads), so the server starts and answers MCP introspection even with no
# network. Mount your own workspace (charter.yaml + data) at /workspace to govern
# real data:
#   docker run -i --rm -v "$PWD:/workspace" datacharter-mcp
#
# Build:  docker build -t datacharter-mcp .
# Run:    docker run -i --rm datacharter-mcp
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/datacharter/datacharter"
LABEL org.opencontainers.image.title="DataCharter MCP server"
LABEL org.opencontainers.image.description="Local-first, contract-governed, PII-masked SQL over MCP."
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Pin for reproducible builds from a tagged commit. Bump in the release ritual
# (next to src/datacharter/__init__.py and server.json).
RUN pip install --no-cache-dir datacharter==0.24.4

# Non-root: create an unprivileged user and a writable HOME (DuckDB needs a
# writable HOME for its state/cache) and workspace.
RUN useradd --create-home --uid 10001 charter
ENV HOME=/home/charter

# Bake a CSV-backed demo workspace (no DuckDB extension downloads -> offline-safe).
RUN mkdir -p /workspace/data \
 && printf 'id,region,amount\n1,US,10\n2,US,20\n3,EU,30\n' > /workspace/data/orders.csv \
 && printf 'version: 1\nsources:\n  store:\n    type: csv\n    path: data/orders.csv\n' > /workspace/charter.yaml \
 && chown -R charter:charter /workspace

USER charter
WORKDIR /workspace
CMD ["datacharter", "mcp", "/workspace"]
