"""Which language a text is in, for the languages the calibration knows.

Script decides most of them; Latin-script languages are told apart by their
most frequent function words, which is reliable at the lengths SlopTotal
scores (50 words and up). That includes languages the calibration has no fit
for (Romanian, Catalan, Indonesian, Vietnamese, Swedish, Danish), so they are
reported as unsupported instead of passing as French or Spanish. One-letter
words do not vote: English "I" would read as Polish "i". Anything else is
"other".
"""

import math
import re
from collections import Counter

FUNCTION_WORDS = {
    "en": "the of and to in is that it for was on with as are this be by not have",
    "es": "de la que el en y los se del las un por con no una para es su al lo",
    "fr": "de la le et les des en un une du est que dans pour qui pas sur au par",
    "de": "der die und in den von zu das mit sich des auf für ist im nicht ein eine dem",
    "pt": "de que o a do da em um para é com não uma os no se na por mais",
    "it": "di che e la il un a per in è non una sono del con le si da della",
    "nl": "de van het een en in is dat op te zijn met voor niet aan er die ook",
    "pl": "na nie się do to że jest jak co ale tak od po przez dla oraz jego jej są był była który która które ich jako także tego też może już",
    "tr": "ve bir bu da de için ile olarak çok daha gibi olan en ama sonra kadar ise olduğu değil her göre ancak kendi sadece",
    "ro": "și în este pentru care sunt cu din pe mai fost această acest fiind prin între sau nu ca la",
    "ca": "amb per els les del una que és són també però aquest aquesta seu dels això",
    "id": "yang dan di untuk dengan ini itu dari dalam tidak ada pada akan juga atau",
    "vi": "và của là có được trong cho những với này không người các một đã",
    "sv": "och att det som är för med på inte av till har om ett jag",
    "da": "og at det som er for med på ikke af til har om et jeg",
}
_WORDS = {lang: set(words.split()) for lang, words in FUNCTION_WORDS.items()}
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)
_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_CJK_PUNCTUATION = re.compile(r"[\u3000-\u303f\uff00-\uffef]")
# Chinese and Japanese, Thai, Lao, Myanmar and Khmer: scripts written without
# spaces between words.
_UNSPACED = re.compile(
    r"[\u3040-\u30ff\u4e00-\u9fff\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff]"
)
_LETTER = re.compile(r"[^\W\d_]")
# The SlopBench corpus asks for "about 600 characters" in Chinese and Japanese
# where it asks for "about 300 words" elsewhere.
CJK_CHARACTERS_PER_WORD = 2


def _script_counts(text: str) -> Counter:
    counts: Counter = Counter()
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            counts["hangul"] += 1
        elif 0x3040 <= code <= 0x30FF:
            counts["kana"] += 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts["han"] += 1
        elif 0x0600 <= code <= 0x06FF:
            counts["arabic"] += 1
        elif 0x0900 <= code <= 0x097F:
            counts["devanagari"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif ch.isalpha():
            counts["latin"] += 1
    return counts


def is_unspaced(text: str) -> bool:
    """Whether most of the text's letters are in a script without spaces between words."""
    letters = len(_LETTER.findall(text))
    return letters > 0 and len(_UNSPACED.findall(text)) > letters / 2


def count_words(text: str) -> int:
    """Words separated by spaces, with Chinese and Japanese, which use none,
    counted at CJK_CHARACTERS_PER_WORD characters a word."""
    cjk = len(_CJK.findall(text))
    spaced = len(_CJK_PUNCTUATION.sub(" ", _CJK.sub(" ", text)).split())
    return spaced + math.ceil(cjk / CJK_CHARACTERS_PER_WORD)


def detect_language(text: str) -> str:
    counts = _script_counts(text)
    if not counts:
        return "other"
    script, _ = counts.most_common(1)[0]
    if script in ("han", "kana"):
        return (
            "ja" if counts["kana"] > 0.05 * (counts["han"] + counts["kana"]) else "zh"
        )
    if script == "cyrillic":
        return "uk" if re.search("[іїєґІЇЄҐ]", text) else "ru"
    simple = {"hangul": "ko", "arabic": "ar", "devanagari": "hi"}
    if script in simple:
        return simple[script]
    tokens = [t.lower() for t in _TOKEN.findall(text) if len(t) > 1]
    if not tokens:
        return "other"
    votes = {lang: sum(t in words for t in tokens) for lang, words in _WORDS.items()}
    best = max(votes, key=votes.get)
    return best if votes[best] >= 0.08 * len(tokens) else "other"
