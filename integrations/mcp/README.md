# SlopTotal MCP server

<!-- mcp-name: io.github.pablocaeg/sloptotal -->

Lets AI agents (Claude Code, Claude Desktop, Cursor, VS Code, any MCP client)
check whether a text or a website is AI-generated with
[SlopTotal](https://github.com/pablocaeg/sloptotal): 23 open detection engines,
one calibrated 0-100 score.

| Tool | What it does |
|---|---|
| `analyze_text` | Scores a text (50+ characters; 300+ words is steadier). Returns `overall_score`, `overall_verdict`, `engines_flagged`, each engine's score and verdict, the language and a report link. |
| `analyze_url` | Fetches a public page, extracts its main text and scores it the same way. |
| `check_website_builder` | Was the site built with an AI app builder (Lovable, v0, Bolt, ...)? Fingerprints with their evidence, plus a quick score of the page copy. |

The score is evidence, not proof; the tool descriptions tell the agent so.

## 1. Run a SlopTotal server

The MCP server is a thin client: it calls a SlopTotal API, by default
`http://localhost:8000`, so the text never leaves your machine.

```bash
docker run -d --name sloptotal -p 8000:8000 -v sloptotal-models:/app/models ghcr.io/pablocaeg/sloptotal
```

The image runs on `linux/amd64` and `linux/arm64` (Apple Silicon included).
The first start downloads about 9 GB of models and needs about 12 GB of RAM;
see the [self-hosting guide](https://sloptotal.com/self-host/) for source
installs, GPU and offline use.

**No room for the models?** Point the MCP server at the public instance with
`SLOPTOTAL_URL=https://api.sloptotal.com`. Everything you analyze is then sent
to sloptotal.com and leaves your machine, and the public instance has rate
limits. Prefer a local server for anything private.

## 2. Add it to your client

Two ways to run the MCP server; pick whichever tool you already have.

- **Docker**: the image `ghcr.io/pablocaeg/sloptotal-mcp` (`linux/amd64` and
  `linux/arm64`, about 60 MB: only the MCP client, no models). It reaches the
  SlopTotal server on your machine through `host.docker.internal`; the
  `--add-host` flag makes that name work on Linux too.
- **uv**: `uvx` fetches the server from this repository; nothing else to
  install.

It is also listed in the [official MCP registry](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.pablocaeg/sloptotal)
as `io.github.pablocaeg/sloptotal`, so clients that browse the registry (VS
Code, for one) can install it from there.

### Claude Code

```bash
# Docker
claude mcp add sloptotal -- docker run -i --rm --add-host=host.docker.internal:host-gateway ghcr.io/pablocaeg/sloptotal-mcp

# uv
claude mcp add sloptotal -- uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp" sloptotal-mcp
```

With the public instance instead of a local server:

```bash
claude mcp add sloptotal -- docker run -i --rm -e SLOPTOTAL_URL=https://api.sloptotal.com ghcr.io/pablocaeg/sloptotal-mcp
# or
claude mcp add sloptotal -e SLOPTOTAL_URL=https://api.sloptotal.com -- uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp" sloptotal-mcp
```

Add `--scope user` to have it in every project.

### Claude Desktop

Settings, Developer, Edit Config (`claude_desktop_config.json`). With Docker:

```json
{
  "mcpServers": {
    "sloptotal": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--add-host=host.docker.internal:host-gateway", "ghcr.io/pablocaeg/sloptotal-mcp"]
    }
  }
}
```

With uv:

```json
{
  "mcpServers": {
    "sloptotal": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp", "sloptotal-mcp"],
      "env": { "SLOPTOTAL_URL": "http://localhost:8000" }
    }
  }
}
```

Restart Claude Desktop. If it cannot find `docker` or `uvx`, put its full path
(`which docker`, `which uvx`) in `command`.

### Cursor

`~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project), the
same blocks as Claude Desktop. With Docker:

```json
{
  "mcpServers": {
    "sloptotal": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--add-host=host.docker.internal:host-gateway", "ghcr.io/pablocaeg/sloptotal-mcp"]
    }
  }
}
```

### VS Code (Copilot agent mode)

`.vscode/mcp.json` in the workspace, or "MCP: Open User Configuration". With
Docker:

```json
{
  "servers": {
    "sloptotal": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "-i", "--rm", "--add-host=host.docker.internal:host-gateway", "ghcr.io/pablocaeg/sloptotal-mcp"]
    }
  }
}
```

With uv:

```json
{
  "servers": {
    "sloptotal": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp", "sloptotal-mcp"],
      "env": { "SLOPTOTAL_URL": "http://localhost:8000" }
    }
  }
}
```

### Any other MCP client

Run either of these as a stdio server:

```bash
docker run -i --rm --add-host=host.docker.internal:host-gateway ghcr.io/pablocaeg/sloptotal-mcp
uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp" sloptotal-mcp
```

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SLOPTOTAL_URL` | `http://localhost:8000` (`http://host.docker.internal:8000` in the Docker image) | The SlopTotal server to call. `https://api.sloptotal.com` sends your text to sloptotal.com. |
| `SLOPTOTAL_TIMEOUT` | `300` | Seconds to wait for a queued scan before giving up. |

## Try it

Ask your agent: "Use SlopTotal to check whether this paragraph was written by
AI: ...", or "Was example.com built with an AI app builder?".

## Develop

The image is built from `Dockerfile` here. Each GitHub release (or a manual
run of the "Publish MCP server" workflow) pushes it to ghcr.io and publishes
`server.json` to the MCP registry; bump the version in `pyproject.toml`,
`src/sloptotal_mcp/__init__.py` and `server.json` (version and image tag)
together, CI checks they match.


```bash
cd integrations/mcp
uv venv && uv pip install -e ".[test]"
.venv/bin/pytest -q          # mocked API, no network
```

MIT licensed, like SlopTotal.
