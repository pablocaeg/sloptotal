#!/usr/bin/env python3
"""
Real-world URL evaluation: known human content vs known AI-generated content.
Tests both /api/quick-score and /api/analyze endpoints.
"""
import asyncio
import httpx
import time
import sys

API_URL = "http://localhost:8000"

# --- Known HUMAN content (pre-AI era or verified human authors) ---
HUMAN_URLS = [
    # Classic journalism / longform (pre-2020)
    ("nytimes_2019", "https://www.nytimes.com/2019/07/20/science/apollo-11-moon-landing.html"),
    ("guardian_2018", "https://www.theguardian.com/science/2018/mar/14/stephen-hawking-obituary"),
    ("atlantic_2013", "https://www.theatlantic.com/magazine/archive/2013/05/the-real-world-of-technology/309289/"),
    # Wikipedia (human-curated encyclopedic content)
    ("wiki_photosynthesis", "https://en.wikipedia.org/wiki/Photosynthesis"),
    ("wiki_roman_empire", "https://en.wikipedia.org/wiki/Roman_Empire"),
    ("wiki_general_relativity", "https://en.wikipedia.org/wiki/General_relativity"),
    # Academic / research (definitely human-written)
    ("paul_graham", "http://paulgraham.com/greatwork.html"),
    ("paul_graham2", "http://paulgraham.com/think.html"),
    # Classic blog posts (pre-AI)
    ("joel_spolsky", "https://www.joelonsoftware.com/2000/04/06/things-you-should-never-do-part-i/"),
    ("codinghorror", "https://blog.codinghorror.com/the-multi-monitor-productivity-myth/"),
]

# --- Known AI-generated content ---
# These are sites/pages known to publish AI-generated content
AI_URLS = [
    # AI-generated articles (content farms, known AI blogs)
    ("ai_blog_1", "https://www.artificialintelligence-news.com/news/what-is-artificial-general-intelligence/"),
    ("ai_news_1", "https://www.unite.ai/what-is-natural-language-processing/"),
]

# --- AI-generated TEXT samples (since reliable AI URLs are hard to find) ---
AI_TEXTS = [
    ("chatgpt_tech", """In today's rapidly evolving technological landscape, artificial intelligence has emerged as a transformative force that is fundamentally reshaping how businesses operate and deliver value to their customers. The integration of machine learning algorithms and natural language processing capabilities has opened up unprecedented opportunities for innovation across virtually every industry sector.

It is important to note that the implications of these advancements extend far beyond mere automation. Organizations that embrace AI-driven solutions are positioning themselves at the forefront of a paradigm shift that promises to redefine the very nature of competitive advantage. From predictive analytics to intelligent process automation, the applications are as diverse as they are impactful.

Furthermore, the democratization of AI tools has made it possible for even small and medium-sized enterprises to leverage sophisticated capabilities that were once the exclusive domain of large corporations with substantial research budgets. This leveling of the playing field represents a significant milestone in the ongoing digital transformation journey that organizations worldwide are undertaking."""),

    ("chatgpt_health", """The relationship between mental health and physical well-being has been the subject of extensive research in recent years, revealing a complex and multifaceted interconnection that underscores the importance of a holistic approach to healthcare. Studies have consistently demonstrated that psychological factors play a crucial role in determining overall health outcomes, highlighting the need for integrated treatment strategies.

One of the key findings in this area is that chronic stress can have profound effects on the immune system, cardiovascular health, and metabolic function. The mechanisms through which psychological distress translates into physical symptoms involve intricate neuroendocrine pathways that are only now beginning to be fully understood. It is worth noting that this mind-body connection operates bidirectionally, with physical health conditions also significantly impacting mental well-being.

In light of these findings, healthcare professionals are increasingly adopting comprehensive approaches that address both psychological and physical dimensions of patient care. This paradigm shift represents a departure from traditional models that treated mental and physical health as separate domains."""),

    ("chatgpt_education", """Education stands at a pivotal crossroads in the 21st century, as traditional pedagogical approaches are being challenged by the rapid advancement of technology and changing societal needs. The integration of digital tools and platforms into the learning environment has created both opportunities and challenges that educators must navigate with care and intentionality.

It is essential to recognize that effective education goes beyond the mere transmission of information. The development of critical thinking skills, emotional intelligence, and adaptability are increasingly recognized as fundamental competencies that students need to thrive in an ever-changing world. This shift in educational philosophy requires a reimagining of curriculum design, assessment methods, and the role of the teacher in the learning process.

Moreover, the COVID-19 pandemic served as a catalyst for the adoption of remote and hybrid learning models, accelerating trends that were already underway. While these new modalities have expanded access to educational resources, they have also highlighted existing inequities in digital infrastructure and literacy that must be addressed to ensure equitable outcomes for all learners."""),

    ("chatgpt_environment", """The global environmental crisis represents one of the most pressing challenges facing humanity in the contemporary era. Climate change, biodiversity loss, and resource depletion are interconnected phenomena that demand urgent and coordinated action at local, national, and international levels. The scientific consensus is clear: without significant changes to current trajectories, the consequences for ecosystems and human societies will be severe and potentially irreversible.

It is crucial to understand that addressing environmental challenges requires a multifaceted approach that encompasses technological innovation, policy reform, and behavioral change. Renewable energy technologies, sustainable agriculture practices, and circular economy models offer promising pathways toward a more sustainable future. However, the transition to these alternatives must be managed carefully to ensure social equity and economic viability.

The role of international cooperation in tackling environmental issues cannot be overstated. Agreements such as the Paris Climate Accord represent important frameworks for collective action, though their effectiveness ultimately depends on the commitment and follow-through of individual nations. As we move forward, it is imperative that environmental considerations are integrated into all aspects of decision-making."""),

    ("chatgpt_business", """In the dynamic world of modern business, strategic leadership has become an indispensable competency for organizations seeking to navigate the complexities of an increasingly interconnected global marketplace. The ability to anticipate market trends, foster innovation, and build resilient organizational cultures distinguishes successful enterprises from those that struggle to adapt to changing circumstances.

Effective leaders understand that sustainable competitive advantage is not built solely on technological capabilities or market positioning, but rather on the cultivation of human capital and organizational learning. By creating environments that encourage experimentation, embrace diversity of thought, and reward collaborative problem-solving, forward-thinking organizations are able to unlock the full potential of their workforce.

Additionally, the growing emphasis on corporate social responsibility and stakeholder capitalism reflects a fundamental evolution in how business success is defined and measured. Companies that integrate environmental, social, and governance considerations into their strategic planning are increasingly recognized as more sustainable and attractive to both investors and talented professionals seeking meaningful work."""),
]

# --- Known HUMAN text samples (verified human-written) ---
HUMAN_TEXTS = [
    ("human_reddit", """honestly the whole situation with my landlord is driving me crazy. like I get that he needs to fix the plumbing but its been THREE WEEKS and I still can't use the kitchen sink properly. called the city housing department yesterday and they said they'd "look into it" which we all know means absolutely nothing lol. my roommate wants to withhold rent but idk if that's even legal here. anyone dealt with something like this before? would really appreciate any advice because I'm at my wit's end here"""),

    ("human_review", """I bought this coffee maker about 6 months ago and I have mixed feelings. The coffee itself tastes great - probably the best drip coffee I've made at home. The thermal carafe keeps it hot for hours which is nice. BUT the water reservoir is a pain to fill because of the weird angle, and the drip tray is too small so you get overflow if you're not careful. Also the "bold" setting doesn't seem to do much different from regular. For the price ($89) it's decent but not amazing. Would I buy it again? Probably, but only because the alternatives in this price range are worse. 3.5/5 stars."""),

    ("human_blog", """So I've been running for about two years now and I want to talk about something nobody warns you about: the mental game is SO much harder than the physical part. Like yeah, your legs hurt and you get out of breath, but the voice in your head telling you to stop? That's the real enemy.

I remember my first 10K - around mile 4 I was absolutely convinced I was dying. Not figuratively, I genuinely thought something was wrong with my body. Turns out I was just... running. My body was fine, my brain was just freaking out because it wasn't used to sustained effort.

The thing that helped me most was honestly just doing it badly. I gave myself permission to walk, to go slow, to look ridiculous. And gradually my brain was like "oh okay I guess we're not dying" and the panic went away. Now I can run a half marathon without that voice showing up until mile 11 or so. Progress!"""),

    ("human_email_style", """Hey Sarah - quick update on the Henderson project. Met with their team on Tuesday and things are... complicated. They basically want to completely redo the database schema which would push us back at least 3 weeks, maybe more. I tried to talk them out of it but Jim (their CTO) is pretty set on it.

I think we have two options: 1) just do what they want and eat the delay, or 2) propose a compromise where we migrate the critical tables first and handle the rest in phase 2. I'm leaning toward option 2 but wanted to get your take before I respond.

Also - totally unrelated - but are you going to Mike's thing on Saturday? Need to know if I should grab an extra ticket. Let me know!"""),

    ("human_essay", """My grandmother's kitchen smelled like cumin and burned sugar. Not because she was a bad cook - she wasn't, she was extraordinary - but because she believed in cooking fearlessly. "The pan should be hot enough to scare you a little," she'd say, tossing onions into oil that crackled and spat like an angry cat.

She never used recipes. I don't mean she had them memorized; I mean she actively distrusted the concept. Measurements were for people who didn't trust their hands. Timers were for people who didn't trust their nose. She cooked the way jazz musicians play - with a framework in mind but always ready to improvise based on what the moment demanded.

I think about her kitchen a lot these days, especially when I watch cooking videos where everything is precisely measured and timed and temperature-controlled. There's nothing wrong with precision, of course. But something is lost when cooking becomes a science experiment instead of a conversation between you and your ingredients."""),
]


async def test_url(client: httpx.AsyncClient, label: str, url: str) -> dict | None:
    """Test a URL against both quick-score and full analyze."""
    try:
        # Quick score
        r = await client.post(
            f"{API_URL}/api/quick-score",
            json={"url": url},
            timeout=30.0,
        )
        if r.status_code != 200:
            print(f"  [{label}] quick-score failed: {r.status_code} {r.text[:100]}")
            return None
        qs = r.json()
        return {
            "label": label,
            "source": url,
            "quick_score": qs.get("score", 0),
            "quick_verdict": qs.get("verdict", "?"),
            "quick_confidence": qs.get("confidence", "?"),
            "engines": qs.get("engines", []),
        }
    except Exception as e:
        print(f"  [{label}] error: {e}")
        return None


async def test_text(client: httpx.AsyncClient, label: str, text: str) -> dict | None:
    """Test raw text against quick-score."""
    try:
        r = await client.post(
            f"{API_URL}/api/quick-score",
            json={"text": text},
            timeout=30.0,
        )
        if r.status_code != 200:
            print(f"  [{label}] quick-score failed: {r.status_code}")
            return None
        qs = r.json()
        return {
            "label": label,
            "source": "text",
            "quick_score": qs.get("score", 0),
            "quick_verdict": qs.get("verdict", "?"),
            "quick_confidence": qs.get("confidence", "?"),
            "engines": qs.get("engines", []),
        }
    except Exception as e:
        print(f"  [{label}] error: {e}")
        return None


async def main():
    # Health check
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_URL}/health", timeout=5.0)
            health = r.json()
            print(f"Server: {health['status']} ({health['engines']} engines)")
        except Exception as e:
            print(f"Server not reachable: {e}")
            sys.exit(1)

    results_human = []
    results_ai = []

    async with httpx.AsyncClient() as client:
        # Test human URLs
        print(f"\n{'='*60}")
        print(f"TESTING HUMAN URLs ({len(HUMAN_URLS)} URLs)")
        print(f"{'='*60}")
        for label, url in HUMAN_URLS:
            r = await test_url(client, label, url)
            if r:
                results_human.append(r)
                print(f"  {label:25s} score={r['quick_score']:5.1f} verdict={r['quick_verdict']:6s} conf={r['quick_confidence']}")

        # Test human texts
        print(f"\n{'='*60}")
        print(f"TESTING HUMAN TEXTS ({len(HUMAN_TEXTS)} samples)")
        print(f"{'='*60}")
        for label, text in HUMAN_TEXTS:
            r = await test_text(client, label, text)
            if r:
                results_human.append(r)
                print(f"  {label:25s} score={r['quick_score']:5.1f} verdict={r['quick_verdict']:6s} conf={r['quick_confidence']}")

        # Test AI URLs
        print(f"\n{'='*60}")
        print(f"TESTING AI URLs ({len(AI_URLS)} URLs)")
        print(f"{'='*60}")
        for label, url in AI_URLS:
            r = await test_url(client, label, url)
            if r:
                results_ai.append(r)
                print(f"  {label:25s} score={r['quick_score']:5.1f} verdict={r['quick_verdict']:6s} conf={r['quick_confidence']}")

        # Test AI texts
        print(f"\n{'='*60}")
        print(f"TESTING AI TEXTS ({len(AI_TEXTS)} samples)")
        print(f"{'='*60}")
        for label, text in AI_TEXTS:
            r = await test_text(client, label, text)
            if r:
                results_ai.append(r)
                print(f"  {label:25s} score={r['quick_score']:5.1f} verdict={r['quick_verdict']:6s} conf={r['quick_confidence']}")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")

    if results_human:
        h_scores = [r["quick_score"] for r in results_human]
        h_avg = sum(h_scores) / len(h_scores)
        h_flagged = sum(1 for s in h_scores if s > 65)
        h_mixed = sum(1 for s in h_scores if 35 < s <= 65)
        h_clean = sum(1 for s in h_scores if s <= 35)
        print(f"\n  Human ({len(results_human)} samples):")
        print(f"    Avg score: {h_avg:.1f}")
        print(f"    Clean (<=35): {h_clean} ({h_clean/len(results_human)*100:.0f}%)")
        print(f"    Mixed (36-65): {h_mixed} ({h_mixed/len(results_human)*100:.0f}%)")
        print(f"    Flagged AI (>65): {h_flagged} ({h_flagged/len(results_human)*100:.0f}%) *** FALSE POSITIVES ***")
        print(f"    Score range: [{min(h_scores):.1f}, {max(h_scores):.1f}]")

    if results_ai:
        a_scores = [r["quick_score"] for r in results_ai]
        a_avg = sum(a_scores) / len(a_scores)
        a_flagged = sum(1 for s in a_scores if s > 65)
        a_mixed = sum(1 for s in a_scores if 35 < s <= 65)
        a_clean = sum(1 for s in a_scores if s <= 35)
        print(f"\n  AI ({len(results_ai)} samples):")
        print(f"    Avg score: {a_avg:.1f}")
        print(f"    Clean (<=35): {a_clean} ({a_clean/len(results_ai)*100:.0f}%) *** MISSED ***")
        print(f"    Mixed (36-65): {a_mixed} ({a_mixed/len(results_ai)*100:.0f}%)")
        print(f"    Flagged AI (>65): {a_flagged} ({a_flagged/len(results_ai)*100:.0f}%)")
        print(f"    Score range: [{min(a_scores):.1f}, {max(a_scores):.1f}]")

    if results_human and results_ai:
        # Per-engine breakdown
        print(f"\n  Per-engine averages:")
        all_engines = set()
        for r in results_human + results_ai:
            for e in r.get("engines", []):
                all_engines.add(e["engine"])

        print(f"  {'Engine':25s} {'Human':>8s} {'AI':>8s} {'Gap':>8s}")
        print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
        for eng_name in sorted(all_engines):
            h_vals = []
            a_vals = []
            for r in results_human:
                for e in r.get("engines", []):
                    if e["engine"] == eng_name:
                        h_vals.append(e["score"])
            for r in results_ai:
                for e in r.get("engines", []):
                    if e["engine"] == eng_name:
                        a_vals.append(e["score"])
            h_mean = sum(h_vals) / len(h_vals) if h_vals else 0
            a_mean = sum(a_vals) / len(a_vals) if a_vals else 0
            gap = a_mean - h_mean
            print(f"  {eng_name:25s} {h_mean:7.1f}% {a_mean:7.1f}% {gap:+7.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
