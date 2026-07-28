# datacharter MCP server (stdio) — the governed, read-only, PII-masked query tools
# (list_sources, list_tables, describe_table, query) over the Model Context Protocol.
#
# Self-contained: installs datacharter on the system PATH and bakes a small demo
# workspace backed by a CSV (a core DuckDB reader — no extension downloads), so the
# server starts and answers MCP introspection even with no network. Mount your own
# workspace (charter.yaml + data) at /workspace to govern real data:
#   docker run -i --rm -v "$PWD:/workspace" datacharter-mcp
#
# Build:  docker build -t datacharter-mcp .
# Run:    docker run -i --rm datacharter-mcp
FROM python:3.12-slim
RUN pip install --no-cache-dir datacharter
# DuckDB needs a writable HOME for its state/cache.
ENV HOME=/tmp
# Bake a CSV-backed demo workspace (no DuckDB extension downloads -> offline-safe).
RUN mkdir -p /workspace/data \
 && printf 'id,region,amount\n1,US,10\n2,US,20\n3,EU,30\n' > /workspace/data/orders.csv \
 && printf 'version: 1\nsources:\n  store:\n    type: csv\n    path: data/orders.csv\n' > /workspace/charter.yaml
WORKDIR /workspace
CMD ["datacharter", "mcp", "/workspace"]
