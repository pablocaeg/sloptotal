import re
import statistics
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict


class StructuralEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Structural Analysis"

    @property
    def description(self) -> str:
        return "Analyzes em-dash usage, sentence uniformity, list density, paragraph regularity, colon patterns"

    @property
    def code(self) -> str:
        return "SA"

    @property
    def engine_type(self) -> str:
        return "linguistic"

    def analyze(self, text: str) -> EngineResult:
        signals = []

        # 1. Em-dash frequency (word—word without spaces)
        em_dashes = len(re.findall(r"\w—\w", text))
        word_count = max(len(text.split()), 1)
        em_dash_rate = (em_dashes / word_count) * 1000
        em_score = min(em_dash_rate / 6.0, 1.0)
        if em_dashes > 0:
            signals.append(f"Em-dashes: {em_dashes} ({em_dash_rate:.1f}/1k words)")

        # 2. Sentence length uniformity
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 3]
        if len(sentences) >= 3:
            lengths = [len(s.split()) for s in sentences]
            mean_len = statistics.mean(lengths)
            stdev = statistics.stdev(lengths)
            cv = stdev / mean_len if mean_len > 0 else 0
            uniformity_score = max(0, 1.0 - (cv / 0.6))
            signals.append(f"Sentence length CV: {cv:.2f} (mean {mean_len:.0f} words)")
        else:
            uniformity_score = 0.0

        # 3. List/bullet density per 1k words
        lines = text.split("\n")
        list_lines = sum(
            1
            for l in lines
            if re.match(r"\s*[-•*]\s", l) or re.match(r"\s*\d+[.)]\s", l)
        )
        list_per_1k = (list_lines / word_count) * 1000
        list_score = min(list_per_1k / 30.0, 1.0)
        if list_lines > 0:
            signals.append(f"List items: {list_lines} ({list_per_1k:.1f}/1k words)")

        # 4. Paragraph length uniformity
        paragraphs = [
            p.strip() for p in text.split("\n\n") if len(p.strip().split()) >= 5
        ]
        if len(paragraphs) >= 3:
            para_lengths = [len(p.split()) for p in paragraphs]
            para_mean = statistics.mean(para_lengths)
            para_stdev = statistics.stdev(para_lengths)
            para_cv = para_stdev / para_mean if para_mean > 0 else 0
            para_score = max(0, 1.0 - (para_cv / 0.5))
            signals.append(f"Paragraph length CV: {para_cv:.2f}")
        else:
            para_score = 0.0

        # 5. Bold/heading density in markdown-like text
        bold_count = len(re.findall(r"\*\*[^*]+\*\*", text))
        heading_count = len(re.findall(r"^#{1,6}\s", text, re.MULTILINE))
        format_density = ((bold_count + heading_count) / word_count) * 1000
        format_score = min(format_density / 10.0, 1.0)
        if bold_count + heading_count > 0:
            signals.append(f"Bold/heading elements: {bold_count + heading_count}")

        # 6. Colon density per 1k words
        colon_count = text.count(":")
        colon_density = (colon_count / word_count) * 1000
        # AI: 18-39/1k, Human: 0-17/1k. Threshold >8 starts scoring.
        colon_score = min(max(colon_density - 8, 0) / 15.0, 1.0)
        if colon_density > 8:
            signals.append(f"Colon density: {colon_density:.1f}/1k words")

        # 7. Colon-introduced definitions ("Term: Explanation")
        colon_defs = len(
            re.findall(r"[A-Z][a-z]+(?:\s[A-Z]?[a-z]+){0,3}:\s[A-Z]", text)
        )
        colon_def_score = min(colon_defs / 3.0, 1.0)
        if colon_defs > 0:
            signals.append(f"Colon definitions: {colon_defs}")

        # Weighted scoring — colon signals are the strongest modern-AI discriminators
        # (em-dashes, para CV, bold/heading often score 0 on scraped text)
        final_score = (
            em_score * 0.08
            + uniformity_score * 0.08
            + list_score * 0.12
            + para_score * 0.07
            + format_score * 0.05
            + colon_score * 0.30
            + colon_def_score * 0.30
        )

        detail_str = (
            "; ".join(signals) if signals else "No structural anomalies detected."
        )

        return EngineResult(
            engine_name=self.name,
            score=round(final_score, 3),
            verdict=score_to_engine_verdict(final_score),
            details=detail_str,
            description=self.description,
        )
