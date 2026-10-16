"""Entry point of the GitHub Action in action.yml: score files, write a job summary."""

import glob
import json
import os
import sys

from sloptotal import SlopTotal, SlopTotalError

MIN_CHARS = 50


def main() -> int:
    patterns = os.environ["FILES"].split()
    threshold = (
        float(os.environ["FAIL_ABOVE"]) if os.environ.get("FAIL_ABOVE") else None
    )
    files = sorted(
        {
            path
            for pattern in patterns
            for path in glob.glob(pattern, recursive=True)
            if os.path.isfile(path)
        }
    )
    if not files:
        print(f"::warning::No files matched {' '.join(patterns)}")

    rows, failed = [], False
    with SlopTotal() as api:
        for path in files:
            text = open(path, encoding="utf-8", errors="replace").read()
            if len(text.strip()) < MIN_CHARS:
                continue
            try:
                report = api.analyze(text=text)
            except SlopTotalError as error:
                print(f"::error file={path}::{error}")
                failed = True
                continue
            over = threshold is not None and report.score > threshold
            failed = failed or over
            if over:
                print(
                    f"::error file={path}::Scores {report.score} ({report.verdict}), above {threshold}. {report.url}"
                )
            rows.append(
                {
                    "file": path,
                    "score": report.score,
                    "verdict": report.verdict,
                    "words": report.word_count,
                    "report_url": report.url,
                    "over_threshold": over,
                }
            )

    summary = ["| File | Score | Verdict | Words | Report |", "|---|---|---|---|---|"]
    summary += [
        f"| `{r['file']}` | {r['score']} | {r['verdict']} | {r['words']} | [open]({r['report_url']}) |"
        for r in rows
    ]
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### SlopTotal\n\n" + "\n".join(summary) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"results={json.dumps(rows)}\n")
    print("\n".join(summary))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
