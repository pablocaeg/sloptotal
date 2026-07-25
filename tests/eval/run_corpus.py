"""Run the labelled corpus through the live API and record every engine's output.

Keeps the `details` string too, because DivEye and Readability report their
internal coefficient of variation there -- that is what we need in order to
recalibrate their thresholds from data instead of guessing.
"""
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.sloptotal.com/api/analyze"
corpus = json.load(open("corpus.json"))


def analyze(item):
    try:
        req = urllib.request.Request(
            API,
            data=json.dumps({"text": item["text"]}).encode(),
            headers={"Content-Type": "application/json",
                     "Origin": "https://sloptotal.com"},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        return {
            "label": item["label"],
            "model": item["model"],
            "domain": item.get("domain"),
            "overall": d["overall_score"],
            "verdict": d["overall_verdict"],
            "engines": {e["engine_name"]: e["score"] for e in d["engine_results"]},
            "details": {e["engine_name"]: e.get("details", "") for e in d["engine_results"]},
        }
    except Exception as e:
        return {"label": item["label"], "model": item["model"], "error": str(e)[:120]}


with ThreadPoolExecutor(max_workers=2) as ex:
    results = list(ex.map(analyze, corpus))

ok = [r for r in results if "error" not in r]
bad = [r for r in results if "error" in r]
print(f"analysed ok={len(ok)} failed={len(bad)}")
for b in bad[:5]:
    print("   ERR", b["model"], b["error"])

json.dump(ok, open("corpus_results.json", "w"))
print("wrote corpus_results.json")
