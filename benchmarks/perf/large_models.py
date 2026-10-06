"""Speed and accuracy of ways to run the three large classifiers faster.

Desklib, ReMoDetect and SuperAnnotate are the critical path of every full
analysis: the other 20 engines finish while these are still scoring windows.
Each variant is timed on real texts of increasing length and compared with
the current code on a fixed accuracy set, engine by engine; `decide.py` turns
those engine deltas into verdict changes.

Variants, all scoring one window at a time with each engine's own
`_score_chunk` (one batched forward pass over every window was measured
slower at two threads, with identical scores):
  baseline    the current engine: 510-token windows every 256 tokens, at most
              MAX_WINDOWS (8) spread across the text
  threads4    the current engine with four torch threads instead of two
  int8        the current windows, Linear layers quantized to int8
  cap4        at most 4 windows
  no_overlap  windows every 510 tokens instead of 256

The accuracy texts carry the production engine scores, which are the
baseline. A variant is scored only where it can differ: cap4 and no_overlap
on texts whose window plan changes, int8 on a fixed sample.

Usage: SLOPTOTAL_TORCH_THREADS=2 python benchmarks/perf/large_models.py texts.json out.json
"""

import json
import os
import random
import sys
import time

import torch

from app.engines import classifier_desklib, classifier_remodetect, classifier_superannotate
from app.engines.base import MAX_WINDOWS, window_starts

THREADS = int(os.environ.get("SLOPTOTAL_TORCH_THREADS", "2"))
WINDOW = 510
STRIDE = 256
INT8_SAMPLE = 60
ENGINES = {
    "classifier_desklib": (classifier_desklib, "ClassifierDesklibEngine"),
    "classifier_remodetect": (classifier_remodetect, "ClassifierReMoDetectEngine"),
    "classifier_superannotate": (classifier_superannotate, "ClassifierSuperAnnotateEngine"),
}
PLANS = {"int8": (STRIDE, MAX_WINDOWS), "cap4": (STRIDE, 4), "no_overlap": (WINDOW, MAX_WINDOWS)}


def plan(n_tokens: int, stride: int, cap: int) -> list[int]:
    return [0] if n_tokens <= WINDOW else window_starts(n_tokens, WINDOW, stride, cap)


def score(module, model, tokenizer, text, stride, cap):
    tokens = tokenizer.encode(text, add_special_tokens=False)
    if len(tokens) <= WINDOW:
        return round(module._score_chunk(text, model, tokenizer), 3)
    scores = []
    for start in window_starts(len(tokens), WINDOW, stride, cap):
        ids = tokens[start : start + WINDOW]
        if len(ids) < 20:
            break
        scores.append(module._score_chunk(tokenizer.decode(ids, skip_special_tokens=True), model, tokenizer))
    return round(sum(scores) / len(scores), 3)


def timed(fn, *args):
    started = time.perf_counter()
    fn(*args)
    return round(time.perf_counter() - started, 3)


def main():
    texts = json.load(open(sys.argv[1]))
    out_path = sys.argv[2]
    out = {"timing": [], "scores": {}, "checked": {}}
    sample = set(random.Random(0).sample([t["id"] for t in texts["accuracy"]], INT8_SAMPLE))

    for key, (module, cls) in ENGINES.items():
        torch.set_num_threads(THREADS)
        model, tokenizer = module._load_model()
        engine = getattr(module, cls)()
        baseline = {t["id"]: t["engines"][key] for t in texts["accuracy"]}
        out["scores"].setdefault("baseline", {})[key] = baseline
        out["scores"].setdefault("threads4", {})[key] = baseline
        n_tokens = {t["id"]: len(tokenizer.encode(t["text"], add_special_tokens=False)) for t in texts["accuracy"]}

        engine.analyze("Warm up the model once before timing it.")
        for threads, variant in ((THREADS, "baseline"), (4, "threads4")):
            torch.set_num_threads(threads)
            for item in texts["timing"]:
                out["timing"].append({"engine": key, "variant": variant, "words": item["words"],
                                      "seconds": timed(engine.analyze, item["text"])})
        torch.set_num_threads(THREADS)

        check = [t for t in texts["accuracy"] if 600 < n_tokens[t["id"]] < 3000][:3]
        out["checked"][key] = [
            [baseline[t["id"]], score(module, model, tokenizer, t["text"], STRIDE, MAX_WINDOWS)] for t in check
        ]

        quantized = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
        for variant, (stride, cap) in PLANS.items():
            m = quantized if variant == "int8" else model
            for item in texts["timing"]:
                out["timing"].append({"engine": key, "variant": variant, "words": item["words"],
                                      "seconds": timed(score, module, m, tokenizer, item["text"], stride, cap)})
            scores = dict(baseline)
            for t in texts["accuracy"]:
                tid = t["id"]
                differs = tid in sample if variant == "int8" else (
                    plan(n_tokens[tid], stride, cap) != plan(n_tokens[tid], STRIDE, MAX_WINDOWS))
                if differs:
                    scores[tid] = score(module, m, tokenizer, t["text"], stride, cap)
            out["scores"].setdefault(variant, {})[key] = scores
            json.dump(out, open(out_path, "w"))
            print(key, variant, "done", flush=True)
        del quantized


if __name__ == "__main__":
    main()
