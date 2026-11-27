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

The server runs with [uv](https://docs.astral.sh/uv/) (`uvx`), which fetches
it from this repository; nothing else to install.

### Claude Code

```bash
claude mcp add sloptotal -- uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp" sloptotal-mcp
```

With the public instance instead of a local server:

```bash
claude mcp add sloptotal -e SLOPTOTAL_URL=https://api.sloptotal.com -- uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp" sloptotal-mcp
```

Add `--scope user` to have it in every project.

### Claude Desktop

Settings, Developer, Edit Config (`claude_desktop_config.json`):

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

Restart Claude Desktop. If it cannot find `uvx`, put its full path
(`which uvx`) in `command`.

### Cursor

`~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project), the
same block as Claude Desktop:

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

### VS Code (Copilot agent mode)

`.vscode/mcp.json` in the workspace, or "MCP: Open User Configuration":

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

Run `uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=integrations/mcp" sloptotal-mcp`
as a stdio server.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SLOPTOTAL_URL` | `http://localhost:8000` | The SlopTotal server to call. `https://api.sloptotal.com` sends your text to sloptotal.com. |
| `SLOPTOTAL_TIMEOUT` | `300` | Seconds to wait for a queued scan before giving up. |

## Try it

Ask your agent: "Use SlopTotal to check whether this paragraph was written by
AI: ...", or "Was example.com built with an AI app builder?".

## Develop

```bash
cd integrations/mcp
uv venv && uv pip install -e ".[test]"
.venv/bin/pytest -q          # mocked API, no network
```

MIT licensed, like SlopTotal.
