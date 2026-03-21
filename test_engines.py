"""Test all 20 engines across multiple URLs and texts to find consistently failing engines."""
import httpx
import asyncio
import json

API = "http://127.0.0.1:8000/api/analyze"

# Mix of known AI-generated and known human-written content
TEST_CASES = [
    # AI-generated texts (should score HIGH)
    {
        "label": "AI - ChatGPT style essay",
        "expected": "ai",
        "text": (
            "Artificial intelligence has transformed numerous industries in recent years, "
            "fundamentally reshaping the way we approach complex problems. From healthcare to finance, "
            "the applications of machine learning and deep learning have proven to be remarkably versatile. "
            "One of the most significant developments in this field has been the emergence of large language "
            "models, which have demonstrated an unprecedented ability to generate human-like text. These models "
            "are trained on vast corpora of text data, enabling them to capture the nuances of language in ways "
            "that were previously thought to be the exclusive domain of human cognition. The implications of this "
            "technology are far-reaching, raising important questions about the nature of creativity, authorship, "
            "and the future of written communication. As we continue to explore the boundaries of what AI can "
            "achieve, it becomes increasingly clear that we are standing at the precipice of a new era in human "
            "history. The convergence of computational power, algorithmic innovation, and data availability has "
            "created a perfect storm of conditions that are driving rapid advancements in artificial intelligence."
        ),
    },
    {
        "label": "AI - Generic blog post",
        "expected": "ai",
        "text": (
            "In today's rapidly evolving digital landscape, businesses must adapt to stay competitive. "
            "The key to success lies in understanding and leveraging the latest technological trends. "
            "Cloud computing has emerged as a critical infrastructure component, enabling organizations "
            "to scale their operations efficiently. Furthermore, the integration of artificial intelligence "
            "into business processes has opened up new possibilities for automation and optimization. "
            "Companies that embrace these technologies are well-positioned to thrive in the modern economy. "
            "It is essential to recognize that digital transformation is not merely a technological shift; "
            "it represents a fundamental change in how organizations create value and interact with their "
            "customers. By fostering a culture of innovation and continuous improvement, businesses can "
            "navigate the complexities of the digital age with confidence and agility. The path forward "
            "requires a strategic approach that balances technological investment with human capital development."
        ),
    },
    {
        "label": "AI - Listicle style",
        "expected": "ai",
        "text": (
            "There are several key strategies that can help you improve your productivity and achieve your "
            "goals more effectively. First, it is important to establish clear objectives and prioritize your "
            "tasks accordingly. By breaking down larger projects into smaller, manageable steps, you can "
            "maintain focus and avoid feeling overwhelmed. Second, consider implementing time management "
            "techniques such as the Pomodoro method or time blocking to structure your workday more "
            "efficiently. Third, eliminating distractions is crucial for maintaining concentration. This "
            "may involve creating a dedicated workspace, using website blockers, or setting specific times "
            "for checking email and social media. Fourth, regular breaks and physical activity can help "
            "maintain your energy levels and mental clarity throughout the day. Finally, reflecting on your "
            "progress and adjusting your approach as needed ensures that you continue to move forward "
            "effectively. Remember that productivity is not about doing more; it is about doing what matters most."
        ),
    },
    # Human-written texts (should score LOW)
    {
        "label": "Human - Hemingway excerpt style",
        "expected": "human",
        "text": (
            "The old man sat in the corner of the bar and watched the flies on the ceiling. He had been "
            "there since noon and his glass was mostly empty. The bartender came over twice but the old "
            "man just shook his head. Outside it was raining the way it rains in November, gray and "
            "without conviction. Someone put money in the jukebox and a song came on that he remembered "
            "from a long time ago, back when his wife was alive and they used to dance in the kitchen "
            "after dinner. He couldn't remember the name of the song but he could remember the way she "
            "smelled, like lavender soap and cigarettes. That was thirty years ago. Or maybe thirty-five. "
            "Time gets funny when you stop counting. He finished his drink and stood up. His knees hurt. "
            "Everything hurt these days. He put some money on the bar and walked out into the rain."
        ),
    },
    {
        "label": "Human - Casual Reddit post",
        "expected": "human",
        "text": (
            "ok so basically I've been trying to fix this stupid bug for like 3 hours and I finally "
            "figured out what was wrong. turns out I had a typo in my env variable name... POSTGRES_HOST "
            "vs POSTGRESS_HOST (two s's lmao). The error message was completely unhelpful btw, it just "
            "said 'connection refused' which made me think it was a firewall issue so I spent forever "
            "checking iptables and docker networking stuff. I even rebuilt the container twice. Anyway "
            "if anyone else runs into weird connection refused errors with postgres in docker, check "
            "your env vars first before going down the networking rabbit hole. Also protip: use "
            "docker compose exec to test the connection directly from inside the container, that would "
            "have saved me a lot of time. feeling dumb but at least it works now. gonna go get coffee."
        ),
    },
    {
        "label": "Human - Technical writing with personality",
        "expected": "human",
        "text": (
            "Look, I know everyone's excited about microservices but can we talk about when they're "
            "actually a terrible idea? I've seen three startups this year blow months of engineering "
            "time decomposing a monolith that was working fine. The thing is, microservices solve "
            "organizational problems, not technical ones. If you have 5 developers, you don't need "
            "15 services. You need one well-structured app with clear module boundaries. The network "
            "calls alone will kill your latency and the debugging story goes from 'look at the stack "
            "trace' to 'good luck correlating logs across 8 services with slightly different time "
            "zones'. Don't even get me started on distributed transactions. The real question isn't "
            "'should we use microservices' -- it's 'do we have the organizational complexity that "
            "justifies the operational complexity?' Usually the answer is no."
        ),
    },
]

# URLs to test
URL_CASES = [
    {
        "label": "URL - Blog post (Spanish basketball)",
        "expected": "human",
        "url": "https://viveelbasket.blogspot.com/",
    },
    {
        "label": "URL - Paul Graham essay",
        "expected": "human",
        "url": "http://paulgraham.com/greatwork.html",
    },
]


async def test_case(client, case):
    payload = {}
    if "url" in case:
        payload["url"] = case["url"]
    else:
        payload["text"] = case["text"]

    try:
        resp = await client.post(API, json=payload, timeout=120.0)
        if resp.status_code != 200:
            return case["label"], case["expected"], None, f"HTTP {resp.status_code}"
        data = resp.json()
        return case["label"], case["expected"], data, None
    except Exception as e:
        return case["label"], case["expected"], None, str(e)


async def main():
    all_cases = TEST_CASES + URL_CASES

    async with httpx.AsyncClient() as client:
        # Run sequentially to avoid overloading
        results = []
        for case in all_cases:
            print(f"Testing: {case['label']}...")
            result = await test_case(client, case)
            results.append(result)

    # Collect per-engine stats
    engine_stats = {}  # engine_name -> {"correct": 0, "wrong": 0, "scores": [], "details": []}

    print("\n" + "=" * 100)
    print("RESULTS BY TEST CASE")
    print("=" * 100)

    for label, expected, data, error in results:
        print(f"\n--- {label} (expected: {expected}) ---")
        if error:
            print(f"  ERROR: {error}")
            continue

        overall = data.get("overall_score", "?")
        verdict = data.get("overall_verdict", "?")
        print(f"  Overall: {overall} — {verdict}")

        for er in data.get("engine_results", []):
            name = er["engine_name"]
            score = er["score"]
            v = er["verdict"]
            details = er.get("details", "")

            if name not in engine_stats:
                engine_stats[name] = {"correct": 0, "wrong": 0, "scores_ai": [], "scores_human": []}

            # Determine if engine was correct
            # For AI text: score >= 0.4 = correct (flagged as AI)
            # For Human text: score < 0.4 = correct (not flagged)
            if expected == "ai":
                engine_stats[name]["scores_ai"].append(score)
                if score >= 0.4:
                    engine_stats[name]["correct"] += 1
                else:
                    engine_stats[name]["wrong"] += 1
            else:
                engine_stats[name]["scores_human"].append(score)
                if score < 0.4:
                    engine_stats[name]["correct"] += 1
                else:
                    engine_stats[name]["wrong"] += 1

            marker = ""
            if expected == "ai" and score < 0.3:
                marker = " *** MISSED AI ***"
            elif expected == "human" and score > 0.7:
                marker = " *** FALSE POSITIVE ***"

            print(f"  {name:25s}  score={score:.3f}  verdict={v:12s}{marker}")

    # Summary
    total_cases = sum(1 for _, _, d, e in results if d is not None)
    ai_cases = sum(1 for _, exp, d, _ in results if d and exp == "ai")
    human_cases = sum(1 for _, exp, d, _ in results if d and exp == "human")

    print("\n" + "=" * 100)
    print(f"ENGINE ACCURACY SUMMARY ({total_cases} test cases: {ai_cases} AI, {human_cases} human)")
    print("=" * 100)
    print(f"{'Engine':25s} {'Correct':>7s} {'Wrong':>7s} {'Accuracy':>8s}  {'Avg AI':>7s}  {'Avg Human':>9s}  {'Assessment'}")
    print("-" * 100)

    sorted_engines = sorted(engine_stats.items(), key=lambda x: x[1]["correct"] / max(x[1]["correct"] + x[1]["wrong"], 1), reverse=True)

    for name, stats in sorted_engines:
        total = stats["correct"] + stats["wrong"]
        acc = stats["correct"] / total if total > 0 else 0
        avg_ai = sum(stats["scores_ai"]) / len(stats["scores_ai"]) if stats["scores_ai"] else 0
        avg_human = sum(stats["scores_human"]) / len(stats["scores_human"]) if stats["scores_human"] else 0

        if acc >= 0.8:
            assessment = "GOOD"
        elif acc >= 0.6:
            assessment = "OK"
        elif acc >= 0.4:
            assessment = "WEAK"
        else:
            assessment = "BAD — consider removing/downweighting"

        # Special: if avg AI score is very low, engine can't detect AI
        if avg_ai < 0.2:
            assessment = "BROKEN — never detects AI"

        print(f"{name:25s} {stats['correct']:>7d} {stats['wrong']:>7d} {acc:>7.0%}   {avg_ai:>6.3f}   {avg_human:>8.3f}   {assessment}")


if __name__ == "__main__":
    asyncio.run(main())
