# sloptotal

A command line tool, a Python client and an MCP server for
[SlopTotal](https://sloptotal.com): 23 independent AI-text detectors behind one
calibrated 0-100 score, with every engine's vote visible.

```bash
uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=client" sloptotal check essay.md
```

```
essay.md   72.4  Likely AI-generated  (412 words)
  top engines: Desklib DeBERTa 0.99, ReMoDetect 0.95, SuperAnnotate 0.93
  report: https://sloptotal.com/report/?id=3f9c1a7b2d4e
```

## Command line

```bash
sloptotal check draft.md notes.txt         # one line per file
cat post.txt | sloptotal check -           # stdin
sloptotal check --url https://example.com/article
sloptotal check docs/*.md --fail-above 55  # exit 1 if any file scores above 55
sloptotal check essay.md --json            # every engine's score
sloptotal site example.com                 # built with Lovable, v0, Bolt, Base44, Replit?
```

`--fail-above` makes it usable in CI or a pre-commit hook. Scores below 30 are
clean, 45 and up are worth a look, 55 and up read as likely AI. Under about 80
words, or in a language where detection is only experimental, the output says
so: a score is evidence, not a verdict.

## MCP server

Lets Claude, Cursor and other agents check text and sites. Add it to your
client's MCP configuration:

```json
{
  "mcpServers": {
    "sloptotal": {
      "command": "uvx",
      "args": ["--from", "sloptotal[mcp] @ git+https://github.com/pablocaeg/sloptotal#subdirectory=client", "sloptotal", "mcp"]
    }
  }
}
```

Claude Code: `claude mcp add sloptotal -- uvx --from "sloptotal[mcp] @ git+https://github.com/pablocaeg/sloptotal#subdirectory=client" sloptotal mcp`

Tools: `analyze_text`, `analyze_url`, `check_site`. Each result carries the
score, the verdict, the top engines, any caveats (short text, experimental
language) and a link to the full report.

## Python

```python
from sloptotal import SlopTotal

with SlopTotal() as api:
    report = api.analyze(text=open("essay.md").read())
    print(report.score, report.verdict, report.url)
    print(report.top_engines(3))
```

## Your own server

Text goes to the public API at `api.sloptotal.com`, which keeps reports for
30 days. To keep it on your machines, [run SlopTotal yourself](https://github.com/pablocaeg/sloptotal#quick-start)
and point the client at it:

```bash
export SLOPTOTAL_URL=http://localhost:8000
```

MIT licensed.
