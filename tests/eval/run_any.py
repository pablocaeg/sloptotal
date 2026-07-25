"""Run a labelled corpus through the live API, with retries.

Retries matter: pushing to master auto-deploys, which restarts the API container
mid-run and returns 502s from nginx. An earlier measurement silently completed
with only 23 of 110 rows and produced a misleading mean, so failures must be
retried and the final row count must be asserted by the caller.

Usage: python run_any.py <input.json> <output.json>
"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.sloptotal.com/api/analyze"
MAX_TRIES = 5

inp, outp = sys.argv[1], sys.argv[2]
corpus = json.load(open(inp))


def analyze(item):
    last = None
    for attempt in range(MAX_TRIES):
        try:
            req = urllib.request.Request(
                API,
                data=json.dumps({"text": item["text"]}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://sloptotal.com",
                },
            )
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            return {
                "label": item["label"],
                "model": item["model"],
                "domain": item.get("domain"),
                "meta": item.get("meta"),
                "overall": d["overall_score"],
                "verdict": d["overall_verdict"],
                "engines": {e["engine_name"]: e["score"] for e in d["engine_results"]},
                "details": {e["engine_name"]: e.get("details", "") for e in d["engine_results"]},
            }
        except Exception as e:
            last = e
            time.sleep(6 * (attempt + 1))
    return {"label": item["label"], "model": item["model"], "error": str(last)[:140]}


with ThreadPoolExecutor(max_workers=2) as ex:
    results = list(ex.map(analyze, corpus))

ok = [r for r in results if "error" not in r]
bad = [r for r in results if "error" in r]
print(f"{inp}: ok={len(ok)}/{len(corpus)} failed={len(bad)}")
for b in bad[:5]:
    print("   ERR", b["model"], b["error"])
json.dump(ok, open(outp, "w"))
if len(ok) != len(corpus):
    print("INCOMPLETE — do not draw conclusions from this run")
    sys.exit(1)
