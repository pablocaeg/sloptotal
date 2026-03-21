import re
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

HEDGING_PHRASES = [
    "it's worth noting",
    "it is worth noting",
    "it's important to remember",
    "it is important to remember",
    "it's important to note",
    "it is important to note",
    "it's crucial to",
    "it is crucial to",
    "it's essential to",
    "it is essential to",
    "it should be noted",
    "one might argue",
    "it could be argued",
    "some might say",
    "there are those who",
    "many experts believe",
    "studies suggest",
    "research indicates",
    "while there are",
    "although there are",
    "that said",
    "having said that",
    "that being said",
    "with that being said",
    "be that as it may",
    "regardless",
    "irrespective of",
]

BALANCE_PATTERNS = [
    r"on (?:the )?one hand\b.{5,150}\bon the other(?: hand)?",
    r"while .{5,80}, (?:it |there |we |they )",
    r"although .{5,80}, (?:it |there |we |they )",
    r"(?:pros|advantages|benefits) .{5,200}(?:cons|disadvantages|drawbacks)",
]

VAGUE_POSITIVITY = [
    "incredibly important",
    "extremely valuable",
    "truly remarkable",
    "absolutely essential",
    "deeply meaningful",
    "truly transformative",
    "game-changing",
    "world-class",
    "best-in-class",
    "make a difference",
    "positive impact",
    "meaningful change",
    "better future",
    "brighter future",
    "greater good",
    "incredible potential",
    "exciting opportunity",
    "powerful tool",
    "valuable resource",
    "essential guide",
]

FILLER_QUALIFIERS = [
    "very",
    "really",
    "extremely",
    "incredibly",
    "absolutely",
    "definitely",
    "certainly",
    "undoubtedly",
    "undeniably",
    "quite",
    "rather",
    "fairly",
    "somewhat",
    "relatively",
]


class SentimentEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Sentiment & Hedging"

    @property
    def description(self) -> str:
        return "Detects excessive hedging, forced balance, vague positivity, and explanatory patterns"

    @property
    def code(self) -> str:
        return "SH"

    @property
    def engine_type(self) -> str:
        return "linguistic"

    def analyze(self, text: str) -> EngineResult:
        text_lower = text.lower()
        word_count = max(len(text.split()), 1)
        signals = []

        # 1. Hedging phrases
        hedge_count = 0
        for phrase in HEDGING_PHRASES:
            count = text_lower.count(phrase)
            hedge_count += count
        hedge_density = (hedge_count / word_count) * 1000
        hedge_score = min(hedge_density / 4.0, 1.0)
        if hedge_count:
            signals.append(
                f"{hedge_count} hedging phrases ({hedge_density:.1f}/1k words)"
            )

        # 2. Balance patterns
        balance_count = 0
        for pattern in BALANCE_PATTERNS:
            balance_count += len(re.findall(pattern, text_lower, re.DOTALL))
        balance_score = min(balance_count / 3.0, 1.0)
        if balance_count:
            signals.append(f"{balance_count} forced-balance structures")

        # 3. Vague positivity
        vague_count = 0
        for phrase in VAGUE_POSITIVITY:
            vague_count += text_lower.count(phrase)
        vague_density = (vague_count / word_count) * 1000
        vague_score = min(vague_density / 3.0, 1.0)
        if vague_count:
            signals.append(f"{vague_count} vague positive phrases")

        # 4. Qualifier overuse
        qualifier_count = 0
        for word in FILLER_QUALIFIERS:
            qualifier_count += len(re.findall(r"\b" + word + r"\b", text_lower))
        qualifier_density = (qualifier_count / word_count) * 1000
        # Humans use ~5-10 per 1k, AI ~15-25+
        qualifier_score = max(0, min((qualifier_density - 8) / 15.0, 1.0))
        if qualifier_count:
            signals.append(
                f"{qualifier_count} filler qualifiers ({qualifier_density:.1f}/1k words)"
            )

        # 5. Explanatory "this/these" pattern
        explanatory_verbs = len(
            re.findall(
                r"\bThis (?:means|ensures|allows|enables|helps|provides|creates|offers|makes|includes|involves|requires)\b",
                text,
            )
        )
        explanatory_nouns = len(
            re.findall(
                r"\b[Tt]his (?:approach|method|process|tool|feature|system|framework|strategy|solution)\b",
                text,
            )
        )
        explanatory_these = len(
            re.findall(
                r"\b[Tt]hese (?:tools|features|systems|methods|approaches|strategies|solutions|techniques|elements|factors|components|resources)\b",
                text,
            )
        )
        explanatory_count = explanatory_verbs + explanatory_nouns + explanatory_these
        # AI: 3-8 per article, Human: 0-1
        explanatory_score = min(explanatory_count / 4.0, 1.0)
        if explanatory_count > 0:
            signals.append(f"{explanatory_count} explanatory this/these patterns")

        final_score = (
            hedge_score * 0.30
            + balance_score * 0.15
            + vague_score * 0.20
            + qualifier_score * 0.15
            + explanatory_score * 0.20
        )

        detail_str = (
            "; ".join(signals)
            if signals
            else "No excessive hedging or sentiment patterns detected."
        )

        return EngineResult(
            engine_name=self.name,
            score=round(final_score, 3),
            verdict=score_to_engine_verdict(final_score),
            details=detail_str,
            description=self.description,
        )
