"""Falsification test for the `code-detection` vertical.

No AI-generated code is needed to settle this. If source code that is
unambiguously human -- CPython stdlib modules, written and reviewed in the open
years before any LLM existed -- is reported as AI-generated, then the engines
cannot support a code-detection claim, and a page selling that capability to
"engineering leads" is overclaiming.
"""
import json
import urllib.request

API = "https://api.sloptotal.com/api/analyze"

FILES = [
    "/usr/lib/python3.12/textwrap.py",
    "/usr/lib/python3.12/difflib.py",
    "/usr/lib/python3.12/calendar.py",
    "/usr/lib/python3.12/argparse.py",
    "/usr/lib/python3.12/dataclasses.py",
    "/usr/lib/python3.12/fractions.py",
]


def analyze(text):
    req = urllib.request.Request(
        API,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json", "Origin": "https://sloptotal.com"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


print(f"{'stdlib module':22} {'score':>6}  verdict")
print("-" * 62)
rows = []
for path in FILES:
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"{path}: unreadable ({e})")
        continue
    # Take a contiguous body chunk, skipping the licence/docstring header.
    body = src[500:4000]
    try:
        d = analyze(body)
    except Exception as e:
        print(f"{path.split('/')[-1]:22} ERROR {e}")
        continue
    rows.append((path.split("/")[-1], d["overall_score"], d["overall_verdict"]))
    print(f"{path.split('/')[-1]:22} {d['overall_score']:6.1f}  {d['overall_verdict']}")

if rows:
    flagged = [r for r in rows if r[1] >= 60]
    susp = [r for r in rows if 40 <= r[1] < 60]
    print(
        f"\n{len(rows)} human stdlib modules: "
        f"{len(flagged)} scored >=60 'Likely AI', {len(susp)} scored 40-60 'Suspicious'"
    )
    json.dump(rows, open("code_test_results.json", "w"), indent=1)
