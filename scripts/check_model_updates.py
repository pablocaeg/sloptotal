#!/usr/bin/env python3
"""Report drift between the locally cached model revisions and HuggingFace.

Why this exists
---------------
No engine passes `revision=` to `from_pretrained`, so every cold start resolves
each model's `main` branch to whatever is current. Models therefore update
themselves — but silently, and only when the HF cache is cold. Two consequences:

  * An upstream re-train can change scores with no code change and no signal,
    which invalidates the calibration in tests/eval/ without anyone noticing.
  * Conversely, on a warm cache (the production box bind-mounts
    /srv/sloptotal/models) an upstream fix is never picked up at all.

This script makes both visible. It does not mutate anything.

Usage
-----
    python scripts/check_model_updates.py               # human-readable
    python scripts/check_model_updates.py --json        # machine-readable
    python scripts/check_model_updates.py --quiet       # only print drift

Exit status is 1 when drift is found, so cron/CI can alert on it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Every model any engine loads. Keep in sync with app/engines/*.
# The three bare ids are legacy aliases that HF redirects to a canonical org.
MODELS = [
    "gpt2-medium",
    "distilgpt2",
    "roberta-base-openai-detector",
    "FacebookAI/roberta-large",
    "fakespot-ai/roberta-base-ai-text-detection-v1",
    "Oxidane/tmr-ai-text-detector",
    "ShantanuT01/BERT-tiny-RAID",
    "MayZhou/e5-small-lora-ai-generated-detector",
    "SuperAnnotate/ai-detector-low-fpr",
    "desklib/ai-text-detector-v1.01",
    "hyunseoki/ReMoDetect-deberta",
    "Hello-SimpleAI/chatgpt-detector-roberta",
]

HF_API = "https://huggingface.co/api/models/{}"


def cache_root() -> Path:
    """Resolve the HF hub cache, honouring HF_HOME as the app sets it."""
    hf_home = os.getenv("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def local_revisions(model: str, root: Path) -> list[str]:
    """Snapshot dirs present locally for a model, newest mtime first."""
    d = root / f"models--{model.replace('/', '--')}" / "snapshots"
    if not d.is_dir():
        return []
    snaps = [p for p in d.iterdir() if p.is_dir()]
    snaps.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in snaps]


def remote_revision(model: str, timeout: float = 30.0) -> tuple[str | None, str | None]:
    """Return (sha, lastModified) for the model's main branch, or (None, err)."""
    req = urllib.request.Request(
        HF_API.format(model),
        headers={"User-Agent": "sloptotal-model-check/1.0"},
    )
    token = os.getenv("HF_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        return d.get("sha"), d.get("lastModified")
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # network, DNS, JSON
        return None, str(e)[:80]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--quiet", action="store_true", help="only report drift")
    args = ap.parse_args()

    root = cache_root()
    rows = []
    for model in MODELS:
        local = local_revisions(model, root)
        sha, meta = remote_revision(model)

        # A model can have several snapshot dirs (a partial earlier fetch, or
        # tokenizer and weights resolved at different times). It is current if
        # ANY cached snapshot matches upstream -- so report the matching one,
        # not just the most recently touched, or the states look contradictory.
        matching = next((r for r in local if sha and r[:12] == sha[:12]), None)

        if sha is None:
            state = "unreachable"
        elif not local:
            state = "not-cached"
        elif matching:
            state = "current"
        else:
            state = "STALE"

        rows.append(
            {
                "model": model,
                "state": state,
                "local": (matching or local[0])[:12] if local else None,
                "local_snapshots": len(local),
                "remote": sha[:12] if sha else None,
                "remote_modified": meta if sha else None,
                "error": None if sha else meta,
            }
        )

    drift = [r for r in rows if r["state"] in ("STALE", "not-cached")]

    if args.json:
        print(json.dumps({"cache": str(root), "rows": rows, "drift": len(drift)}, indent=2))
    else:
        if not args.quiet:
            print(f"HF cache: {root}\n")
            print(f"{'model':50} {'state':12} {'local':14} {'remote':14} modified")
            print("-" * 108)
            for r in rows:
                extra = f" (+{r['local_snapshots'] - 1} other snapshot)" if r["local_snapshots"] > 1 else ""
                print(
                    f"{r['model'][:50]:50} {r['state']:12} "
                    f"{str(r['local'] or '-'):14} {str(r['remote'] or '-'):14} "
                    f"{str(r['remote_modified'] or r['error'] or '')[:10]}{extra}"
                )
        if drift:
            print(f"\n{len(drift)} model(s) need attention:")
            for r in drift:
                print(f"  {r['state']:11} {r['model']}")
            print(
                "\nAn upstream change invalidates the calibration in tests/eval/.\n"
                "After updating, re-run the corpora and check the numbers in\n"
                "tests/eval/FINDINGS.md still hold."
            )
        elif not args.quiet:
            print("\nAll models match their upstream main branch.")

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
