# The SlopTotal MCP server as a stdio container: only the thin MCP client,
# no models. It calls a SlopTotal API (by default one running on the host).
#   docker run -i --rm --add-host=host.docker.internal:host-gateway ghcr.io/pablocaeg/sloptotal-mcp
FROM python:3.15-slim

# The official MCP registry checks this label to verify who owns the image.
LABEL io.modelcontextprotocol.server.name="io.github.pablocaeg/sloptotal"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # A SlopTotal server on the host machine (docker run -p 8000:8000 ...).
    SLOPTOTAL_URL=http://host.docker.internal:8000

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . && rm -rf /src && useradd --create-home --uid 10001 mcp

USER mcp
WORKDIR /home/mcp
ENTRYPOINT ["sloptotal-mcp"]
