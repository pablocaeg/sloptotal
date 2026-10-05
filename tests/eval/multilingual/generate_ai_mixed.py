"""More AI text per language, from four model families other than DeepSeek.

With one generator, a detector tuned on this set could be learning one model's
habits rather than machine text. Each language's 40 Wikipedia topics are
spread over four cheap models (ten each) with the same prompts and lengths as
generate_ai.py, so a model fitted on DeepSeek text can be tested on the others.

Runs through OpenRouter (OPENROUTER_API_KEY) with SlopBench's request helper,
which keeps reasoning out of the reply.

Usage: OPENROUTER_API_KEY=... python generate_ai_mixed.py [lang ...]
"""

import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx

HERE = Path(__file__).parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


multilingual = _load("multilingual_generate_ai", HERE / "generate_ai.py")
SLOPBENCH = Path(os.environ.get("SLOPBENCH_DIR", HERE.parent / "slopbench"))
slopbench = _load("slopbench_generate_ai", SLOPBENCH / "generate_ai.py")

OUT = HERE / "corpus"
MODELS = ["openai/gpt-6-luna", "qwen/qwen3.8-flash", "mistralai/mistral-small-2603", "meta-llama/llama-4-maverick"]


def generate(client: httpx.Client, topic: str, lang: str, style: str, model: str) -> dict | None:
    text = slopbench.chat(client, model, multilingual.prompt(topic, lang, style), 1200)
    if not text or slopbench.leaked_instructions(text):
        return None
    sample = multilingual.cut(text.replace("*", "").replace("#", ""), lang)
    if not sample:
        return None
    return {
        "label": "ai",
        "model": model,
        "domain": style,
        "lang": lang,
        "topic": topic,
        "meta": f"{model} temperature={slopbench.TEMPERATURE} generated={date.today().isoformat()}",
        "text": sample,
    }


def main() -> None:
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "X-Title": "SlopTotal multilingual"}
    langs = sys.argv[1:] or list(multilingual.LANGUAGES)
    with httpx.Client(headers=headers, timeout=180) as client:
        for lang in langs:
            path = OUT / f"ai-mixed-{lang}.json"
            if path.exists():
                continue
            topics = [row["topic"] for row in json.loads((OUT / f"wikipedia-{lang}.json").read_text())]
            jobs = [
                (topic, lang, "encyclopedia" if i % 2 == 0 else "blog", MODELS[i % len(MODELS)])
                for i, topic in enumerate(topics)
            ]
            with ThreadPoolExecutor(max_workers=8) as pool:
                rows = [row for row in pool.map(lambda job: generate(client, *job), jobs) if row]
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
            print(f"{lang}: {len(rows)}/{len(jobs)} samples", flush=True)


if __name__ == "__main__":
    main()
