import re
from collections import Counter
from app.engines.base import BaseEngine
from app.schemas import EngineResult, score_to_engine_verdict

AI_OPENERS = [
    r"in today'?s (?:rapidly )?(?:evolving|changing|digital|modern)",
    r"in (?:the|a) (?:world|era|age|landscape) (?:where|of|that)",
    r"when it comes to",
    r"in the realm of",
    r"(?:are you |ever )?(?:looking|wondering|struggling|trying) to",
    r"(?:have you ever )?wondered (?:what|how|why)",
    r"let'?s (?:dive|explore|take a (?:closer )?look|unpack|break down)",
    r"(?:imagine|picture) (?:this|a world)",
    r"(?:whether you'?re|if you'?re) (?:a |an )?(?:seasoned|beginner|new)",
    r"(?:in|throughout) (?:recent years|the past decade|today'?s society)",
    r"(?:it'?s no (?:secret|surprise)|there'?s no denying) that",
    r"as (?:technology|the world|we|society) continues to",
    r"the (?:rise|emergence|advent|proliferation) of",
]

AI_CLOSERS = [
    r"in conclusion,?",
    r"(?:in summary|to summarize|to sum up),?",
    r"(?:ultimately|at the end of the day),?",
    r"as we (?:navigate|move forward|look ahead|continue)",
    r"(?:the (?:future|road ahead) (?:is|looks|holds))",
    r"(?:by|through) (?:embracing|leveraging|harnessing|adopting)",
    r"(?:only time will tell|the possibilities are (?:endless|limitless))",
    r"(?:it'?s clear|one thing is (?:clear|certain)) that",
    r"(?:in this ever|in our ever|in an ever)",
    r"(?:remember|keep in mind),? (?:it'?s|the)",
]

FILLER_PATTERNS = [
    r"not only\b.{3,60}\bbut also",
    r"on (?:the )?one hand\b.{3,120}\bon the other(?: hand)?",
    r"it(?:'?s| is) (?:important|worth|crucial|essential|interesting) to (?:note|remember|mention|highlight|consider|understand|recognize)",
    r"(?:this|that|which) (?:is to say|means that|implies that|suggests that|indicates that)",
    r"(?:needless to say|it goes without saying)",
    r"(?:first and foremost|last but not least)",
    r"(?:without (?:a )?doubt|beyond (?:a )?shadow of (?:a )?doubt)",
    r"(?:serves as|acts as) (?:a )?(?:powerful |key |critical )?(?:reminder|testament|example|illustration)",
]


class FormulaicEngine(BaseEngine):
    @property
    def name(self) -> str:
        return "Formulaic Patterns"

    @property
    def description(self) -> str:
        return "Detects cliché AI openings, closings, filler patterns, and structural repetition"

    @property
    def code(self) -> str:
        return "FP"

    @property
    def engine_type(self) -> str:
        return "linguistic"

    def analyze(self, text: str) -> EngineResult:
        text_lower = text.lower()
        word_count = max(len(text.split()), 1)
        found = []

        # Check openers (only first 200 chars)
        opener_text = text_lower[:300]
        for pattern in AI_OPENERS:
            match = re.search(pattern, opener_text)
            if match:
                found.append(f'opener: "{match.group()}"')
                break  # Only count one opener

        # Check closers (only last 300 chars)
        closer_text = text_lower[-400:]
        for pattern in AI_CLOSERS:
            match = re.search(pattern, closer_text)
            if match:
                found.append(f'closer: "{match.group()}"')
                break

        # Check filler patterns throughout
        filler_count = 0
        for pattern in FILLER_PATTERNS:
            matches = re.findall(pattern, text_lower)
            filler_count += len(matches)
            for m in matches[:2]:
                snippet = m if isinstance(m, str) else m[0]
                found.append(f'filler: "{snippet[:50]}"')

        # 4. Sentence starter repetition
        sents = re.split(r"(?<=[.!?])\s+", text)
        first_words = []
        for s in sents:
            s = s.strip()
            if s:
                word = re.match(r"[A-Za-z]+", s)
                if word:
                    first_words.append(word.group().lower())
        if len(first_words) >= 5:
            starter_counts = Counter(first_words)
            repeated = sum(c for c in starter_counts.values() if c > 1)
            repeat_ratio = repeated / len(first_words)
            # NOTE: common English words (the, it, in) naturally repeat —
            # only extreme repetition (>55%) with content words is meaningful
            starter_score = min(max(repeat_ratio - 0.55, 0) / 0.25, 1.0)
            if repeat_ratio > 0.55:
                top_starters = starter_counts.most_common(3)
                top_str = ", ".join(f'"{w}"x{c}' for w, c in top_starters if c > 1)
                found.append(f"starter repetition: {repeat_ratio:.0%} ({top_str})")
        else:
            starter_score = 0.0

        # 5. Heading → bullet-list pattern
        lines = text.split("\n")
        heading_list_count = 0
        i = 0
        while i < len(lines) - 1:
            line = lines[i].strip()
            # Short line without period = potential heading
            if (
                line
                and len(line) < 60
                and not line.endswith(".")
                and not re.match(r"\s*[-•*]\s", line)
            ):
                # Check if next lines are bullet/list items
                j = i + 1
                bullet_run = 0
                while j < len(lines) and re.match(r"\s*[-•*]\s", lines[j].strip()):
                    bullet_run += 1
                    j += 1
                if bullet_run >= 2:
                    heading_list_count += 1
                    i = j
                    continue
            i += 1
        # AI: 3-5 per article, Human: 0-1
        heading_list_score = min(heading_list_count / 3.0, 1.0)
        if heading_list_count > 0:
            found.append(f"heading→list sections: {heading_list_count}")

        # Weighted scoring — openers/closers/fillers catch 2023-era cliché AI,
        # heading→list catches structured AI output, starters low-weight (noisy)
        opener_score = 1.0 if any("opener" in f for f in found) else 0.0
        closer_score = 1.0 if any("closer" in f for f in found) else 0.0
        filler_density = (filler_count / word_count) * 1000
        filler_score = min(filler_density / 5.0, 1.0)

        final_score = (
            opener_score * 0.20
            + closer_score * 0.15
            + filler_score * 0.30
            + starter_score * 0.05
            + heading_list_score * 0.30
        )

        if found:
            detail_str = f"Found {len(found)} formulaic patterns: " + "; ".join(
                found[:8]
            )
        else:
            detail_str = "No formulaic AI patterns detected."

        return EngineResult(
            engine_name=self.name,
            score=round(final_score, 3),
            verdict=score_to_engine_verdict(final_score),
            details=detail_str,
            description=self.description,
        )
