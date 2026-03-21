import re
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

# (word_or_phrase, weight) — higher weight = stronger AI signal
AI_MARKERS = [
    # Tier 1: Very strong AI signals (weight 3)
    ("delve", 3),
    ("tapestry", 3),
    ("multifaceted", 3),
    ("ever-evolving", 3),
    ("thought-provoking", 3),
    ("it's important to note", 3),
    ("it's worth noting", 3),
    ("in today's digital age", 3),
    ("in today's rapidly evolving", 3),
    ("let's dive in", 3),
    # Tier 2: Strong signals (weight 2)
    ("landscape", 2),
    ("navigate", 2),
    ("leverage", 2),
    ("foster", 2),
    ("pivotal", 2),
    ("nuanced", 2),
    ("robust", 2),
    ("holistic", 2),
    ("synergy", 2),
    ("paradigm", 2),
    ("encompass", 2),
    ("intricate", 2),
    ("comprehensive", 2),
    ("underscores", 2),
    ("underscore", 2),
    ("realm", 2),
    ("cornerstone", 2),
    ("underpinning", 2),
    ("facilitating", 2),
    ("harnessing", 2),
    ("spearheading", 2),
    ("revolutionize", 2),
    ("groundbreaking", 2),
    ("cutting-edge", 2),
    ("game-changer", 2),
    ("deep dive", 2),
    ("at the forefront", 2),
    ("at its core", 2),
    ("in the realm of", 2),
    ("it is crucial", 2),
    ("it is essential", 2),
    ("plays a crucial role", 2),
    ("serves as a testament", 2),
    ("is a testament to", 2),
    ("a myriad of", 2),
    ("plethora", 2),
    # Tier 3: Moderate signals (weight 1)
    ("crucial", 1),
    ("enhance", 1),
    ("dynamic", 1),
    ("innovative", 1),
    ("streamline", 1),
    ("optimize", 1),
    ("elevate", 1),
    ("empower", 1),
    ("stakeholder", 1),
    ("ecosystem", 1),
    ("actionable", 1),
    ("seamless", 1),
    ("seamlessly", 1),
    ("furthermore", 1),
    ("moreover", 1),
    ("consequently", 1),
    ("nevertheless", 1),
    ("in conclusion", 1),
    ("ultimately", 1),
    ("in essence", 1),
    ("it is important to", 1),
    ("not only", 1),
    ("but also", 1),
    ("on the other hand", 1),
    ("having said that", 1),
    ("that being said", 1),
    ("with that in mind", 1),
    ("in this context", 1),
    ("in light of", 1),
    ("as we navigate", 1),
    ("when it comes to", 1),
    ("it goes without saying", 1),
    ("needless to say", 1),
    ("at the end of the day", 1),
    ("the bottom line", 1),
    ("key takeaway", 1),
    ("food for thought", 1),
    ("resonate", 1),
    ("aligns with", 1),
    ("bolster", 1),
    ("catalyst", 1),
    ("testament", 1),
    ("arguably", 1),
    ("notably", 1),
    ("specifically", 1),
    ("essentially", 1),
    ("fundamentally", 1),
    ("inherently", 1),
    ("intricacies", 1),
    # Spanish markers
    ("en el panorama actual", 2),
    ("es importante destacar", 2),
    ("cabe señalar", 2),
    ("en este contexto", 2),
    ("sin lugar a dudas", 2),
    ("en la era digital", 2),
    ("resulta fundamental", 2),
    ("no cabe duda", 2),
]


class LinguisticEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Linguistic Markers"

    @property
    def description(self) -> str:
        return "Detects AI-preferred words and phrases (delve, tapestry, landscape...)"

    @property
    def code(self) -> str:
        return "LM"

    @property
    def engine_type(self) -> str:
        return "linguistic"

    def analyze(self, text: str) -> EngineResult:
        text_lower = text.lower()
        word_count = max(len(text.split()), 1)

        total_weight = 0
        found_markers = []

        for marker, weight in AI_MARKERS:
            count = len(re.findall(r"\b" + re.escape(marker) + r"\b", text_lower))
            if count > 0:
                total_weight += count * weight
                found_markers.append(
                    f'"{marker}" ×{count}' if count > 1 else f'"{marker}"'
                )

        # Density: weighted hits per 1000 words
        density = (total_weight / word_count) * 1000

        # Score mapping: 0 density = 0.0, 15+ density = 1.0
        score = min(density / 15.0, 1.0)

        if found_markers:
            top = found_markers[:8]
            detail_str = f"Found {len(found_markers)} AI markers (density: {density:.1f}/1k words): {', '.join(top)}"
            if len(found_markers) > 8:
                detail_str += f" and {len(found_markers) - 8} more"
        else:
            detail_str = "No significant AI linguistic markers detected."

        return EngineResult(
            engine_name=self.name,
            score=round(score, 3),
            verdict=score_to_engine_verdict(score),
            details=detail_str,
            description=self.description,
        )
