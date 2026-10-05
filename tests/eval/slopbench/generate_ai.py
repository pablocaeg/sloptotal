"""SlopBench, AI side: one machine-written counterpart for every human sample.

Each human sample carries the seed it was written for (headline, question,
prompt, title...). The counterpart is asked for with that seed, in the same
register and at about the same length, by one of ten models chosen
by a stable hash of the sample id, so every family covers every domain.
Four are free models and six are cheap ones (at most $1 per million output
tokens). Reasoning is switched off, or kept low and out of the reply for models
that cannot switch it off. ONLY=free or ONLY=cheap
runs one group, so the free daily quota and the paid budget can be spent apart.

Prompts are what a person would actually type. No instruction tries to evade
detection; the adversarial variants (paraphrased, "humanized", AI-polished
human text) are built separately by make_hard.py so they can be reported apart.

Runs through OpenRouter. The key is read from OPENROUTER_API_KEY and never
written anywhere; every output records model, prompt, temperature and date.
Resumable: samples already generated are skipped.

Usage: OPENROUTER_API_KEY=... python generate_ai.py [source ...]
"""

import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx

CORPUS = Path(__file__).parent / "corpus"
API = "https://openrouter.ai/api/v1/chat/completions"
WORKERS = int(os.environ.get("WORKERS", "8"))
TEMPERATURE = 0.8
REASONING_ROOM = 3000
REASONING_OFF = {"enabled": False}
REASONING_LOW = {"effort": "low", "exclude": True}

FREE_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "qwen/qwen3.8-27b:free",
]
CHEAP_MODELS = [
    "openai/gpt-6-luna",
    "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3.8-flash",
    "meta-llama/llama-4-maverick",
    "mistralai/mistral-small-2603",
    "z-ai/glm-5.3-flash",
]
MODELS = FREE_MODELS + CHEAP_MODELS
ONLY = os.environ.get("ONLY", "")
FALLBACK = os.environ.get("FALLBACK") == "1"

PROMPTS = {
    "news-ccnews": "Write a news article with the headline “{headline}”. About {words} words.",
    "news-wikinews": "Write a news article with the headline “{headline}”. About {words} words.",
    "news-bbc": "Write a news report of about {words} words on this story: {summary}",
    "social-reddit": "Write a Reddit comment for r/{subreddit}, about {words} words, making this point: {point}",
    "explanation-eli5": "Answer this r/explainlikeimfive question in about {words} words: {question}",
    "qa-stackexchange": "Answer this question from {site} in about {words} words:\n\n{question}",
    "academic-arxiv": "Write the abstract for a paper in {field} titled “{title}”. About {words} words.",
    "creative-writingprompts": "Write a short story of about {words} words for this writing prompt: {prompt}",
    "review-amazon": "Write a {sentiment} Amazon product review titled “{title}”. About {words} words.",
    "encyclopedia-wikipedia": "Write an encyclopedia article section of about {words} words about {title}.",
    "classics-gutenberg": "Write a passage of about {words} words in the style of {author}'s {title}.",
    "essay-toefl": "Write a TOEFL independent writing essay of about {words} words answering: {prompt}",
    "essay-hewlett": "Write an essay of about {words} words, as an 8th-grade student, answering: {prompt}",
    "essay-college": "Write a college admission essay of about {words} words for this prompt: {prompt}",
}
PLAIN = "Reply with the text only, as plain prose: no title, no headings, no preamble."

INFER_MODEL = "qwen/qwen3.8-27b:free" if ONLY == "free" else "deepseek/deepseek-v4.1-flash"
INFER = (
    "Here is a student essay. Reply with only the essay question or prompt it answers, "
    "as one sentence, in the neutral wording an exam would use.\n\n{text}"
)

_lock = threading.Lock()


class OutOfCredits(RuntimeError):
    """Every further paid request would fail too; stop the run."""


def chat(client: httpx.Client, model: str, prompt: str, max_tokens: int, temperature: float = TEMPERATURE) -> str | None:
    for attempt in range(4):
        r = client.post(
            API,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens + REASONING_ROOM,
                "reasoning": REASONING_OFF if attempt == 0 else REASONING_LOW,
            },
        )
        if r.status_code == 200 and "choices" in r.json():
            content = (r.json()["choices"][0]["message"].get("content") or "").strip()
            if content:
                return content
            print(f"  {model}: empty reply (attempt {attempt + 1})", flush=True)
            continue
        print(f"  {model}: HTTP {r.status_code} {r.text[:160]} (attempt {attempt + 1})", flush=True)
        if r.status_code == 402:
            raise OutOfCredits(r.text[:200])
        if r.status_code == 403 or "per-day" in r.text:
            return None
        time.sleep(5 * (attempt + 1))
    return None


def infer_prompts(client: httpx.Client, source: str) -> None:
    """The essay sets come without their prompts; ask a model which question each
    essay answers, once, and store it as the seed."""
    path = CORPUS / f"human-{source}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    missing = [r for r in rows if not r.get("seed")]
    if not missing:
        return

    def one(row: dict) -> None:
        question = chat(client, INFER_MODEL, INFER.format(text=row["text"]), 120, temperature=0)
        if question:
            row["seed"] = {"prompt": question.strip('"“” '), "prompt_inferred_by": INFER_MODEL}

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, missing))
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


LEAK = re.compile(
    r"^(we need to|the user (wants|asks)|let me|okay,|i need to|thinking)|plain prose: no title|no preamble"
    r"|^i('m| am) sorry|(cannot|can't|unable to) (fulfill|comply with|help with) (this|the|that|your) request",
    re.I,
)


def leaked_instructions(text: str) -> bool:
    """A reasoning model narrating the request, or a refusal, instead of an answer."""
    return bool(LEAK.search(text[:300]))


def model_for(sample_id: str) -> str:
    """The sample's model; with FALLBACK=1, a cheap one in place of a free one,
    because the free endpoints are throttled upstream to a few requests a minute."""
    digest = int(hashlib.sha256(sample_id.encode()).hexdigest(), 16)
    model = MODELS[digest % len(MODELS)]
    if FALLBACK and model in FREE_MODELS:
        return CHEAP_MODELS[(digest // len(MODELS)) % len(CHEAP_MODELS)]
    return model


def request_text(sample: dict) -> str:
    words = max(60, round(sample["words"] / 10) * 10)
    seed = {k: v for k, v in sample["seed"].items() if k != "prompt_inferred_by"}
    return PROMPTS[sample["source"]].format(words=words, **seed) + " " + PLAIN


def generate(client: httpx.Client, sample: dict) -> dict | None:
    model = model_for(sample["id"])
    prompt = request_text(sample)
    for _ in range(3):
        text = chat(client, model, prompt, max(400, sample["words"] * 3))
        if text and not leaked_instructions(text):
            break
    if not text or len(text.split()) < 40 or leaked_instructions(text):
        return None
    return {
        "id": f"ai-{sample['id']}",
        "pair": sample["id"],
        "label": "ai",
        "source": sample["source"],
        "domain": sample["domain"],
        "model": model,
        "prompt": prompt,
        "temperature": TEMPERATURE,
        "date": date.today().isoformat(),
        "text": text,
        "words": len(text.split()),
    }


def run(source: str, client: httpx.Client) -> None:
    if source.startswith("essay-"):
        infer_prompts(client, source)
    human = [json.loads(line) for line in (CORPUS / f"human-{source}.jsonl").read_text().splitlines()]
    out_path = CORPUS / f"ai-{source}.jsonl"
    done = {json.loads(line)["pair"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
    todo = [s for s in human if s["id"] not in done and s.get("seed")]
    if ONLY == "free":
        todo = [s for s in todo if model_for(s["id"]) in FREE_MODELS]
    elif ONLY == "cheap":
        todo = [s for s in todo if model_for(s["id"]) in CHEAP_MODELS]

    def one(sample: dict) -> None:
        row = generate(client, sample)
        if row:
            with _lock, open(out_path, "a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, todo))
    total = len(out_path.read_text().splitlines()) if out_path.exists() else 0
    print(f"{source}: {total}/{len(human)} generated", flush=True)


def main() -> None:
    key = os.environ["OPENROUTER_API_KEY"]
    headers = {"Authorization": f"Bearer {key}", "X-Title": "SlopBench"}
    sources = sys.argv[1:] or [p.name[6:-6] for p in sorted(CORPUS.glob("human-*.jsonl")) if p.name[6:-6] in PROMPTS]
    with httpx.Client(headers=headers, timeout=180) as client:
        for source in sources:
            try:
                run(source, client)
            except OutOfCredits as error:
                raise SystemExit(f"Out of OpenRouter credits, stopping: {error}") from None


if __name__ == "__main__":
    main()
