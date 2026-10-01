"""sloptotal check FILE... | sloptotal site URL | sloptotal mcp"""

import argparse
import json
import sys
from pathlib import Path

from sloptotal.client import Report, SlopTotal, SlopTotalError

SHORT_TEXT_WORDS = 80


def _read(source: str) -> str:
    return (
        sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    )


def _summary(name: str, report: Report, top: int) -> str:
    lines = [
        f"{name}  {report.score:5.1f}  {report.verdict}  ({report.word_count} words)"
    ]
    if report.word_count < SHORT_TEXT_WORDS:
        lines.append("  note: under 80 words the score is a weak signal")
    if report.language_support != "supported":
        lines.append(
            f"  note: detection in this language ({report.language}) is {report.language_support}"
        )
    if top:
        lines.append(
            "  top engines: "
            + ", ".join(
                f"{name} {score:.2f}" for name, score in report.top_engines(top)
            )
        )
    lines.append(f"  report: {report.url}")
    return "\n".join(lines)


def check(args: argparse.Namespace) -> int:
    results, failed = [], False
    with SlopTotal(args.server) as api:
        targets = [("url", u) for u in args.url] + [("file", f) for f in args.files]
        if not targets:
            targets = [("file", "-")]
        for kind, target in targets:
            try:
                report = (
                    api.analyze(url=target)
                    if kind == "url"
                    else api.analyze(text=_read(target))
                )
            except (SlopTotalError, ValueError, OSError) as error:
                print(f"{target}: {error}", file=sys.stderr)
                failed = True
                continue
            name = "stdin" if target == "-" else target
            over = args.fail_above is not None and report.score > args.fail_above
            failed = failed or over
            if args.json:
                results.append(
                    {
                        "source": name,
                        "score": report.score,
                        "verdict": report.verdict,
                        "word_count": report.word_count,
                        "language": report.language,
                        "language_support": report.language_support,
                        "report_url": report.url,
                        "engines": report.engines,
                        "over_threshold": over,
                    }
                )
            else:
                print(_summary(name, report, args.top))
    if args.json:
        print(json.dumps(results, indent=2))
    return 1 if failed else 0


def site(args: argparse.Namespace) -> int:
    try:
        with SlopTotal(args.server) as api:
            result = api.check_site(args.url)
    except SlopTotalError as error:
        print(f"{args.url}: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    builders = (result.get("site") or {}).get("builders", [])
    if not builders:
        print(f"{args.url}: no AI app builder fingerprints")
    for builder in builders:
        print(f"{args.url}: {builder['name']} ({builder['confidence']})")
        for evidence in builder.get("evidence", []):
            print(f"  - {evidence}")
    copy = result.get("text")
    if copy:
        print(f"  page copy: {copy['score']} on the quick scan")
    return 0


def mcp(_: argparse.Namespace) -> int:
    try:
        from sloptotal.mcp_server import run
    except ImportError:
        print(
            'The MCP server needs the extra: pip install "sloptotal[mcp]"',
            file=sys.stderr,
        )
        return 1
    run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sloptotal", description="Detect AI-generated text with 23 engines."
    )
    parser.add_argument(
        "--server",
        help="API base URL (default: $SLOPTOTAL_URL or https://api.sloptotal.com)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("check", help="Score text files, stdin (-) or URLs")
    p.add_argument(
        "files", nargs="*", help="Files to check; '-' or nothing reads stdin"
    )
    p.add_argument(
        "--url", action="append", default=[], help="A public URL to check (repeatable)"
    )
    p.add_argument("--json", action="store_true", help="Print JSON instead of text")
    p.add_argument(
        "--fail-above",
        type=float,
        metavar="SCORE",
        help="Exit 1 when a score is above SCORE (e.g. 55)",
    )
    p.add_argument(
        "--top", type=int, default=3, help="How many engines to list (default 3)"
    )
    p.set_defaults(handler=check)

    p = commands.add_parser("site", help="Was a website built with an AI app builder?")
    p.add_argument("url")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=site)

    p = commands.add_parser(
        "mcp", help="Run the MCP server (stdio) for Claude, Cursor and other agents"
    )
    p.set_defaults(handler=mcp)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
