# sloptotal: AI text detector for the command line, CI and AI agents

<!-- mcp-name: io.github.pablocaeg/sloptotal -->

A command line tool, an MCP server, a GitHub Action and a Python client for
[SlopTotal](https://sloptotal.com): 23 independent AI-text detectors behind one
calibrated 0-100 score, with every engine's vote visible. It tells you whether a
text, a web page or a whole site reads as written by ChatGPT, Claude, Gemini,
Llama or another LLM, and how far to trust that answer.

```bash
uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=client" sloptotal check essay.md
```

```
essay.md   72.4  Likely AI-generated  (412 words)
  top engines: Desklib DeBERTa 0.99, SuperAnnotate 0.95, Fakespot 0.93
  report: https://sloptotal.com/report/?id=3f9c1a7b2d4e
```

What the score means: under 30 is clean; 45 and up is worth a look, and only
about 5 in 100 human texts score that high; 55 and up reads as likely AI, which
fewer than 2 in 100 human texts reach. Under about 80 words, or in a language
where detection is only experimental, the output says so. A score is evidence,
not a verdict. The numbers behind it are in
[SlopBench](https://github.com/pablocaeg/sloptotal/tree/master/tests/eval/slopbench).

## Command line

```bash
sloptotal check draft.md notes.txt         # one line per file
cat post.txt | sloptotal check -           # stdin
sloptotal check --url https://example.com/article
sloptotal check docs/*.md --fail-above 55  # exit 1 if any file scores above 55
sloptotal check essay.md --json            # every engine's score
sloptotal site example.com                 # built with Lovable, v0, Bolt, Base44, Replit?
```

`--fail-above` makes it a CI or pre-commit check:

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: sloptotal
      name: AI text check
      entry: uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=client" sloptotal check --fail-above 55
      language: system
      files: \.md$
```

## MCP server for Claude, Cursor and other agents

Three read-only tools: `analyze_text`, `analyze_url` and `check_site`. Each
result carries the score, the verdict, the top engines, any caveats and a link
to the full report, and the server tells the agent that a score is never proof
that a person used AI.

**Claude Code**

```bash
claude mcp add sloptotal -- uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=client" sloptotal mcp
```

**Claude Desktop, Cursor, Windsurf** (`claude_desktop_config.json`, `.cursor/mcp.json`, ...)

```json
{
  "mcpServers": {
    "sloptotal": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/pablocaeg/sloptotal#subdirectory=client", "sloptotal", "mcp"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`)

```json
{
  "servers": {
    "sloptotal": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/pablocaeg/sloptotal#subdirectory=client", "sloptotal", "mcp"]
    }
  }
}
```

Then ask, for example: *"Is this cover letter AI-written?"* or *"Check whether
example.com was built with an AI app builder."*

## GitHub Action

```yaml
- uses: pablocaeg/sloptotal@master
  with:
    files: "docs/**/*.md"
    fail-above: 55        # optional; without it the job only reports
```

Each file's score lands in the job summary with a link to its report, and a
file above `fail-above` fails the job with an annotation on it.

## Python

```python
from sloptotal import SlopTotal

with SlopTotal() as api:
    report = api.analyze(text=open("essay.md").read())
    print(report.score, report.verdict, report.url)
    print(report.top_engines(3))

    site = api.check_site("example.com")
```

## Privacy and your own server

Text goes to the public API at `api.sloptotal.com`, which keeps reports for
30 days and never sends text to third parties. To keep everything on your own
machines, [run SlopTotal yourself](https://github.com/pablocaeg/sloptotal#quick-start)
(one `docker run`) and point the client at it:

```bash
export SLOPTOTAL_URL=http://localhost:8000
```

MIT licensed.
