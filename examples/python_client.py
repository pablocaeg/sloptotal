import argparse
import json

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze text and scan a website with the SlopTotal API."
    )
    parser.add_argument("text", help="At least 50 characters of text to analyze")
    parser.add_argument("site_url", help="Website URL to scan")
    parser.add_argument(
        "--base",
        default="http://localhost:8000",
        help="SlopTotal server URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    args.base = args.base.rstrip("/")
    return args


def analyze_text(client: httpx.Client, text: str) -> dict:
    response = client.post("/api/analyze", json={"text": text})
    response.raise_for_status()
    analysis = response.json()
    return {
        "overall_score": analysis["overall_score"],
        "overall_verdict": analysis["overall_verdict"],
        "engine_results": [
            {
                "engine_name": engine["engine_name"],
                "score": engine["score"],
                "verdict": engine["verdict"],
            }
            for engine in analysis["engine_results"]
        ],
    }


def main() -> int:
    args = parse_args()

    try:
        with httpx.Client(base_url=args.base, timeout=120.0) as client:
            analysis = analyze_text(client, args.text)

            print(
                f"Overall score: {analysis['overall_score']:.1f}/100 "
                f"({analysis['overall_verdict']})"
            )
            print("Top five engines:")
            top_engines = sorted(
                analysis["engine_results"],
                key=lambda engine: engine["score"],
                reverse=True,
            )[:5]
            for engine in top_engines:
                print(f"  {engine['engine_name']}: {engine['score']:.1%}")

            response = client.post(
                "/api/scan/site",
                json={"url": args.site_url},
            )
            response.raise_for_status()
            site_scan = response.json()

            print("\nSite scan:")
            print(json.dumps(site_scan, indent=2))

    except httpx.HTTPStatusError as error:
        print(f"API returned HTTP {error.response.status_code}: {error.response.text}")
        return 1
    except httpx.RequestError as error:
        print(f"Could not connect to the SlopTotal API: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
