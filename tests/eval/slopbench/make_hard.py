"""SlopBench, hard cases: the text people actually argue about.

Four variants, each built from a fixed sample of the base corpus (the same
samples on every run) and reported separately from it:

  ai-paraphrased     AI text reworded by a second, different model
  ai-humanized       AI text rewritten the way "humanizer" tools promise to
  human-ai-polished  human text with its style improved by a model
  mixed-continued    a human opening, continued by a model in the same voice

The first two are still AI text; the last two are the grey zone, labelled as
such, where a detector should ideally land in the middle rather than say
"human" or "AI" with confidence.

Usage: OPENROUTER_API_KEY=... python make_hard.py [variant ...]
"""

import json
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx

from generate_ai import CHEAP_MODELS, CORPUS, WORKERS, OutOfCredits, chat, leaked_instructions

PER_SOURCE = int(os.environ.get("HARD_PER_SOURCE", "20"))

VARIANTS = {
    "ai-paraphrased": (
        "ai",
        "ai",
        "Paraphrase the following text. Keep its meaning, tone and length. Reply with the text only.\n\n{text}",
    ),
    "ai-humanized": (
        "ai",
        "ai",
        "Rewrite the following text so it reads like a real person wrote it: vary the sentence length, "
        "use a natural and personal voice, and cut filler, clichés and tidy summaries. Keep the meaning "
        "and roughly the length. Reply with the text only.\n\n{text}",
    ),
    "human-ai-polished": (
        "human",
        "human-ai-polished",
        "Improve the clarity, grammar and flow of the following text. Keep the author's meaning, voice "
        "and length. Reply with the text only.\n\n{text}",
    ),
    "mixed-continued": (
        "human",
        "mixed",
        "Continue the following text for about {words} more words, in the same voice and style, so the "
        "whole reads as one piece. Reply with the continuation only.\n\n{text}",
    ),
}

_lock = threading.Lock()


def base_samples(kind: str, variant: str) -> list[dict]:
    rng = random.Random(variant)
    picked = []
    for path in sorted(CORPUS.glob(f"{kind}-*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows = [r for r in rows if r["label"] in ("human", "ai") and r["words"] >= 120]
        picked += rng.sample(rows, min(PER_SOURCE, len(rows)))
    return picked


def other_model(row: dict, rng: random.Random) -> str:
    """A cheap model other than the one that wrote the base text."""
    return rng.choice([m for m in CHEAP_MODELS if m != row.get("model")])


def build(variant: str, client: httpx.Client) -> None:
    kind, label, template = VARIANTS[variant]
    out_path = CORPUS / f"hard-{variant}.jsonl"
    done = {json.loads(line)["base"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
    rng = random.Random(f"{variant}-models")
    todo = [(row, other_model(row, rng)) for row in base_samples(kind, variant)]
    todo = [(row, model) for row, model in todo if row["id"] not in done]

    def one(item: tuple[dict, str]) -> None:
        row, model = item
        if variant == "mixed-continued":
            head = " ".join(row["text"].split()[: row["words"] // 2])
            head = head[: head.rfind(".") + 1] or head
            prompt = template.format(text=head, words=row["words"] - len(head.split()))
            continuation = chat(client, model, prompt, row["words"] * 3)
            text = f"{head}\n\n{continuation}" if continuation else None
            split_at = len(head.split())
        else:
            prompt = template.format(text=row["text"])
            text = chat(client, model, prompt, max(400, row["words"] * 3))
            split_at = None
        if not text or len(text.split()) < 60 or leaked_instructions(text):
            return
        result = {
            "id": f"{variant}-{row['id']}",
            "base": row["id"],
            "label": label,
            "variant": variant,
            "source": row["source"],
            "domain": row["domain"],
            "base_model": row.get("model", "human"),
            "model": model,
            "prompt": template.split("\n\n")[0],
            "date": date.today().isoformat(),
            "text": text,
            "words": len(text.split()),
        }
        if split_at:
            result["human_words"] = split_at
        with _lock, open(out_path, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, todo))
    print(f"{variant}: {len(out_path.read_text().splitlines())} samples", flush=True)


def main() -> None:
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "X-Title": "SlopBench"}
    with httpx.Client(headers=headers, timeout=180) as client:
        for variant in sys.argv[1:] or list(VARIANTS):
            try:
                build(variant, client)
            except OutOfCredits as error:
                raise SystemExit(f"Out of OpenRouter credits, stopping: {error}") from None


if __name__ == "__main__":
    main()
