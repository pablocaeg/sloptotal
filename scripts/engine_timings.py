"""Print how long each engine takes on texts of different lengths.

Runs against a live SlopTotal server and reads the per-engine ``elapsed_ms``
that ``/api/analyze`` returns:

    uvicorn app.main:app --port 8000 &
    python scripts/engine_timings.py                    # 100, 500 and 2000 words
    python scripts/engine_timings.py --base http://localhost:8000 --words 200 1000

Each text is made unique so the report cache cannot answer for the engines.
"""

import argparse
import sys
import uuid

import httpx

SENTENCES = (
    "The committee reviewed the proposal on Tuesday and asked for a second "
    "round of figures before voting.",
    "Rain kept most of the visitors indoors, so the museum was quieter than "
    "the organisers had hoped.",
    "He rewrote the opening paragraph three times and still did not like how "
    "it sounded out loud.",
    "A small bakery near the station started selling rye loaves in the "
    "morning, and they were gone by nine.",
    "Nobody could say exactly when the bridge had been repainted, only that "
    "the colour was wrong.",
)


def make_text(words: int) -> str:
    """About `words` words of plain prose, unique per call."""
    out: list[str] = []
    i = 0
    while len(out) < words:
        out.extend(SENTENCES[i % len(SENTENCES)].split())
        i += 1
    # A throwaway first sentence keeps the text hash different on every run.
    return f"Note {uuid.uuid4().hex[:8]}. " + " ".join(out[:words])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--words", type=int, nargs="+", default=[100, 500, 2000])
    args = parser.parse_args()
    base = args.base.rstrip("/")

    timings: dict[str, dict[int, float | None]] = {}
    for words in args.words:
        resp = httpx.post(
            f"{base}/api/analyze", json={"text": make_text(words)}, timeout=900
        )
        resp.raise_for_status()
        for result in resp.json()["engine_results"]:
            timings.setdefault(result["engine_name"], {})[words] = result.get(
                "elapsed_ms"
            )

    width = max((len(name) for name in timings), default=6)
    header = f"{'engine':<{width}}" + "".join(f"{w:>11} words" for w in args.words)
    print(header)
    print("-" * len(header))
    ranked = sorted(timings.items(), key=lambda kv: -(kv[1].get(args.words[-1]) or 0))
    for name, by_words in ranked:
        cells = "".join(
            f"{by_words[w]:>8.0f} ms   "
            if by_words.get(w) is not None
            else f"{'-':>14}"
            for w in args.words
        )
        print(f"{name:<{width}}{cells}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
