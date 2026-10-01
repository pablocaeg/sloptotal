"""AI-written text in each language, on the same topics as the Wikipedia set.

Pairing topics matters: otherwise a detector could score well by telling
subjects apart rather than authors. Half the samples are encyclopedic, half
are blog-style, so the set is not a single register.

Generated with any OpenAI-compatible endpoint (DeepSeek by default); every
sample records the model, style and temperature. The key is read from the
environment and never written anywhere.

Usage: LLM_API_KEY=... python generate_ai.py [lang ...]
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx

from languages import LANGUAGES, cut, is_cjk

OUT = Path(__file__).parent / "corpus"
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
TEMPERATURE = 0.9

STYLES = {
    "encyclopedia": "Write an informative, encyclopedia-style passage about “{topic}”.",
    "blog": "Write an engaging blog post about “{topic}” for a general audience.",
}


def prompt(topic: str, lang: str, style: str) -> str:
    name = LANGUAGES[lang][0]
    length = "about 600 characters" if is_cjk(lang) else "about 300 words"
    return (
        f"{STYLES[style].format(topic=topic)} Write it in {name}, {length}, as continuous prose: "
        "no title, no headings, no bullet points, no Markdown. Reply with the text only."
    )


def generate(client: httpx.Client, topic: str, lang: str, style: str) -> dict | None:
    for _ in range(3):
        try:
            r = client.post(
                "/chat/completions",
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt(topic, lang, style)}],
                    "temperature": TEMPERATURE,
                    "max_tokens": 1200,
                },
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].replace("*", "").replace("#", "")
            sample = cut(text, lang)
            if sample:
                return {
                    "label": "ai",
                    "model": MODEL,
                    "domain": style,
                    "lang": lang,
                    "topic": topic,
                    "meta": f"{MODEL} temperature={TEMPERATURE} generated={date.today().isoformat()}",
                    "text": sample,
                }
        except httpx.HTTPError:
            continue
    return None


def main() -> None:
    key = os.environ["LLM_API_KEY"]
    langs = sys.argv[1:] or list(LANGUAGES)
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {key}"}, timeout=180) as client:
        for lang in langs:
            topics = [row["topic"] for row in json.loads((OUT / f"wikipedia-{lang}.json").read_text())]
            jobs = [(topic, lang, "encyclopedia" if i % 2 == 0 else "blog") for i, topic in enumerate(topics)]
            with ThreadPoolExecutor(max_workers=6) as pool:
                rows = [row for row in pool.map(lambda job: generate(client, *job), jobs) if row]
            (OUT / f"ai-{MODEL}-{lang}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
            print(f"{lang}: {len(rows)}/{len(jobs)} samples", flush=True)


if __name__ == "__main__":
    main()
