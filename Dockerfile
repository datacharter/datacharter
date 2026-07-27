# datacharter MCP server (stdio) — the governed, read-only, PII-masked query tools
# (list_sources, list_tables, describe_table, query) over the Model Context Protocol.
#
# The image ships a demo workspace so the server starts and answers MCP introspection
# out of the box. To govern your own data, mount a workspace (charter.yaml + data) at
# /workspace:  docker run -i --rm -v "$PWD:/workspace" datacharter-mcp
#
# Build:  docker build -t datacharter-mcp .
# Run:    docker run -i --rm datacharter-mcp
FROM python:3.12-slim
RUN pip install --no-cache-dir datacharter
# DuckDB needs a writable HOME for its extension cache.
ENV HOME=/tmp
# Bake a demo workspace (charter.yaml + demo store.db) into the image.
RUN datacharter init /workspace --demo
WORKDIR /workspace
ENTRYPOINT ["datacharter", "mcp", "/workspace"]
