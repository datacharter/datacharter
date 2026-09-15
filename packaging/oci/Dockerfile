# DataCharter MCP HTTP (cluster). OAuth env required at run time for
# --host 0.0.0.0. Build from this commit, not a PyPI pin.
#
#   docker build -f packaging/oci/Dockerfile -t datacharter:dev .
#   docker run --rm -p 8765:8765 \
#     -e DATACHARTER_OAUTH_ISSUER=... \
#     -e DATACHARTER_OAUTH_AUDIENCE=... \
#     -e DATACHARTER_OAUTH_JWKS_URI=... \
#     -v "$PWD:/workspace" datacharter:dev
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/datacharter/datacharter"
LABEL org.opencontainers.image.title="DataCharter MCP HTTP"
LABEL org.opencontainers.image.description="Contract-governed MCP Streamable HTTP. OAuth required off loopback."
LABEL org.opencontainers.image.licenses="Apache-2.0"

RUN useradd --create-home --uid 10001 charter \
 && mkdir -p /workspace \
 && chown charter:charter /workspace
COPY --from=build /install /usr/local
USER 10001
ENV HOME=/home/charter
WORKDIR /workspace
EXPOSE 8765
ENTRYPOINT ["datacharter", "mcp", "--http", "--host", "0.0.0.0", "--port", "8765", "/workspace"]
