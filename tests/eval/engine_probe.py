"""Probe every engine against ground-truth AI and pre-LLM human text.

Human samples are public-domain works published long before any LLM existed,
so any engine that scores them as AI is producing a false positive by
construction -- there is no ambiguity about provenance.
"""
import json
import urllib.request

API = "https://api.sloptotal.com/api/analyze"

SAMPLES = [
    ("AI-slop-markers", "ai", """In the ever-evolving landscape of modern business, it is important to note that organizations must delve into the rich tapestry of digital transformation. Moreover, leveraging synergistic frameworks unlocks unprecedented value for stakeholders. Furthermore, this paradigm shift represents a fundamental reimagining of how enterprises navigate complex challenges. Ultimately, companies that embrace these methodologies will find themselves well-positioned to thrive in an increasingly competitive marketplace, fostering a culture of innovation that permeates every level of the organization."""),

    ("AI-plain-explainer", "ai", """Photosynthesis is the process by which plants convert light energy into chemical energy. This process occurs primarily in the chloroplasts of plant cells, which contain a green pigment called chlorophyll. Chlorophyll absorbs light most efficiently in the blue and red wavelengths while reflecting green light, which is why plants appear green to our eyes. During photosynthesis, plants take in carbon dioxide from the atmosphere and water from the soil. Using light energy, they convert these raw materials into glucose and oxygen. The glucose serves as food for the plant, providing energy for growth and development."""),

    ("Human-MobyDick-1851", "human", """Call me Ishmael. Some years ago--never mind how long precisely--having little or no money in my purse, and nothing particular to interest me on shore, I thought I would sail about a little and see the watery part of the world. It is a way I have of driving off the spleen and regulating the circulation. Whenever I find myself growing grim about the mouth; whenever it is a damp, drizzly November in my soul; whenever I find myself involuntarily pausing before coffin warehouses, and bringing up the rear of every funeral I meet; and especially whenever my hypos get such an upper hand of me, that it requires a strong moral principle to prevent me from deliberately stepping into the street, and methodically knocking people's hats off--then, I account it high time to get to sea as soon as I can."""),

    ("Human-Austen-1813", "human", """It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife. However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered the rightful property of some one or other of their daughters. "My dear Mr. Bennet," said his lady to him one day, "have you heard that Netherfield Park is let at last?" Mr. Bennet replied that he had not. "But it is," returned she; "for Mrs. Long has just been here, and she told me all about it." Mr. Bennet made no answer."""),

    ("Human-Darwin-1859-formal", "human", """When we look to the individuals of the same variety or sub-variety of our older cultivated plants and animals, one of the first points which strikes us, is, that they generally differ much more from each other, than do the individuals of any one species or variety in a state of nature. When we reflect on the vast diversity of the plants and animals which have been cultivated, and which have varied during all ages under the most different climates and treatment, I think we are driven to conclude that this greater variability is simply due to our domestic productions having been raised under conditions of life not so uniform as, and somewhat different from, those to which the parent species have been exposed under nature."""),

    ("Human-informal-casual", "human", """ok so I finally got around to fixing that stupid leaky faucet and honestly what a nightmare. spent like 40 mins under the sink with a wrench that didn't fit, went to the hardware store TWICE, and the guy there looked at me like I was an idiot when I described the part wrong. anyway it's fixed now but my back hurts and I'm never doing plumbing again lol. next time I'm just calling someone. also I dropped a screw down the drain which was fun. dont recommend."""),
]


def analyze(text):
    req = urllib.request.Request(
        API,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json", "Origin": "https://sloptotal.com"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


results = {}
for name, truth, text in SAMPLES:
    d = analyze(text)
    results[name] = {
        "truth": truth,
        "overall": d["overall_score"],
        "verdict": d["overall_verdict"],
        "engines": {e["engine_name"]: e["score"] for e in d["engine_results"]},
    }
    print(f"{name:26} truth={truth:5} overall={d['overall_score']:6.1f}  {d['overall_verdict']}")

json.dump(results, open("/tmp/claude-0/-root/115c8718-8eb5-499a-b970-e492788cad29/scratchpad/probe_results.json", "w"), indent=2)
print("\nwrote probe_results.json")
