"""SlopBench, AI side: one machine-written counterpart for every human sample.

Each human sample carries the seed it was written for (headline, question,
prompt, title...). The counterpart is asked for with that seed, in the same
register and at about the same length, by one of twelve model families chosen
by a stable hash of the sample id, so every family covers every domain.

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
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx

CORPUS = Path(__file__).parent / "corpus"
API = "https://openrouter.ai/api/v1/chat/completions"
WORKERS = int(os.environ.get("WORKERS", "8"))
TEMPERATURE = 0.8

MODELS = [
    "openai/gpt-6.1-sol",
    "openai/gpt-6-luna",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-haiku-4.5",
    "google/gemini-3.8-flash",
    "x-ai/grok-4.3",
    "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3.8-flash",
    "meta-llama/llama-4-maverick",
    "mistralai/mistral-small-2603",
    "moonshotai/kimi-k2.6",
    "z-ai/glm-5.3-flash",
]

PROMPTS = {
    "news-ccnews": "Write a news article with the headline “{headline}”. About {words} words.",
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

INFER_MODEL = "deepseek/deepseek-v4.1-flash"
INFER = (
    "Here is a student essay. Reply with only the essay question or prompt it answers, "
    "as one sentence, in the neutral wording an exam would use.\n\n{text}"
)

_lock = threading.Lock()


def chat(client: httpx.Client, model: str, prompt: str, max_tokens: int, temperature: float = TEMPERATURE) -> str | None:
    for attempt in range(4):
        r = client.post(
            API,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        print(f"  {model}: HTTP {r.status_code} (attempt {attempt + 1})", flush=True)
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


def model_for(sample_id: str) -> str:
    return MODELS[int(hashlib.sha256(sample_id.encode()).hexdigest(), 16) % len(MODELS)]


def request_text(sample: dict) -> str:
    words = max(60, round(sample["words"] / 10) * 10)
    seed = {k: v for k, v in sample["seed"].items() if k != "prompt_inferred_by"}
    return PROMPTS[sample["source"]].format(words=words, **seed) + " " + PLAIN


def generate(client: httpx.Client, sample: dict) -> dict | None:
    model = model_for(sample["id"])
    prompt = request_text(sample)
    text = chat(client, model, prompt, max(400, sample["words"] * 3))
    if not text or len(text.split()) < 40:
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
            run(source, client)


if __name__ == "__main__":
    main()
