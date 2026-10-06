"""Clean timing of the window plans, interleaved, plus accuracy of the combined plan.

large_models.py timed each variant in its own block, so anything else running
on the machine at the time skewed one variant and not the others. Here every
timing text is scored by each plan in a shuffled order, REPEATS times, so the
plans share the same conditions. The combined plan (windows every 510 tokens,
at most 4) is also scored on every accuracy text whose window plan changes,
and written into the large_models.py output as variant "no_overlap_cap4" so
decide.py can compare it.

Usage: PYTHONPATH=.:benchmarks/perf SLOPTOTAL_TORCH_THREADS=2 python benchmarks/perf/retime.py texts.json large_models_out.json retime_out.json
"""

import json
import os
import random
import sys
import time

import torch

from app.engines.base import MAX_WINDOWS
from large_models import ENGINES, STRIDE, WINDOW, plan, score

torch.set_num_threads(int(os.environ.get("SLOPTOTAL_TORCH_THREADS", "2")))
REPEATS = 2
PLANS = {
    "baseline": (STRIDE, MAX_WINDOWS),
    "cap4": (STRIDE, 4),
    "no_overlap": (WINDOW, MAX_WINDOWS),
    "no_overlap_cap4": (WINDOW, 4),
}


def main() -> None:
    texts = json.load(open(sys.argv[1]))
    run = json.load(open(sys.argv[2]))
    out = {"timing": []}
    rng = random.Random(0)
    for key, (module, _) in ENGINES.items():
        model, tokenizer = module._load_model()
        score(module, model, tokenizer, "Warm up the model once before timing it.", STRIDE, MAX_WINDOWS)
        for item in texts["timing"]:
            for _ in range(REPEATS):
                order = list(PLANS)
                rng.shuffle(order)
                for name in order:
                    stride, cap = PLANS[name]
                    started = time.perf_counter()
                    score(module, model, tokenizer, item["text"], stride, cap)
                    out["timing"].append({"engine": key, "variant": name, "words": item["words"],
                                          "seconds": round(time.perf_counter() - started, 3)})
        json.dump(out, open(sys.argv[3], "w"))
        print(key, "timed", flush=True)

        baseline = run["scores"]["baseline"][key]
        combined = dict(baseline)
        for t in texts["accuracy"]:
            n = len(tokenizer.encode(t["text"], add_special_tokens=False))
            if plan(n, WINDOW, 4) != plan(n, STRIDE, MAX_WINDOWS):
                combined[t["id"]] = score(module, model, tokenizer, t["text"], WINDOW, 4)
        run["scores"].setdefault("no_overlap_cap4", {})[key] = combined
        json.dump(run, open(sys.argv[2], "w"))
        print(key, "combined scored", flush=True)


if __name__ == "__main__":
    main()
