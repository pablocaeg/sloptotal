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
from fractions import Fraction

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
    # Catalan shares most of its commonest function words with Spanish (no de la el
    # un en al, as well as que una del), so they voted for Spanish only and Catalan
    # text read as Spanish, a supported language. Listing them here too makes them
    # vote for both, and the Catalan-only forms decide. Those (perquè molt seva
    # doncs què més quan només) are closed-class words from the OPUS/OpenSubtitles
    # list at https://github.com/hermitdave/FrequencyWords that are at least 700
    # per million words in Catalan, are absent or 300 times rarer in the Spanish
    # list, and do not occur in the non-Catalan texts in tests/eval/multilingual.
    "ca": "amb per els les del una que és són també però aquest aquesta seu dels això no de la el un en al perquè molt seva doncs què més quan només",
    "id": "yang dan di untuk dengan ini itu dari dalam tidak ada pada akan juga atau",
    "vi": "và của là có được trong cho những với này không người các một đã",
    "sv": "och att det som är för med på inte av till har om ett jag",
    "da": "og at det som er for med på ikke af til har om et jeg",
    # Finnish, Czech and Hungarian have no fit either, and without them text in
    # these languages fell through to whichever language shares a few short
    # words: Czech read as Polish (a *supported* language, so it was scored
    # under the Polish calibration rather than reported as unsupported).
    # Word lists are the most frequent function words from the OPUS/OpenSubtitles
    # frequency lists at https://github.com/hermitdave/FrequencyWords, keeping
    # the forms that are closed-class and at least two letters.
    "fi": "ja on ei että se oli hän mutta kuin niin myös kun jos tai vain ovat ole tämä siitä",
    # Czech shares ale/do/jako/na/to with Polish, so the list leans on the forms
    # Polish does not have (je, že, jsou, které, při, podle).
    "cs": "je že se na to do ale jako byl jsou nebo pro jeho které který při podle také už",
    "hu": "az és hogy nem is egy de van csak már még meg ha mint volt vagy ami után által lehet",
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
# Thai, Lao, Khmer and Burmese have no such corpus figure, so they come from the
# Universal Declaration of Human Rights (http://efele.net/udhr), whose English text
# is 1,747 words. Counting every character in each script's Unicode block, Thai has
# 8,890 (5.1 a word), Lao 10,196 (5.8), Khmer 10,187 (5.8) and Burmese 14,602 (8.4),
# rounded to a whole number. Like the CJK figure these are characters per word of
# English text, not per word of the language, because the thresholds that use the
# count (short text, lane) are in English words. One formal text is a rough guide.
_UNSPACED_SCRIPTS = (
    (_CJK, CJK_CHARACTERS_PER_WORD),
    (re.compile(r"[\u0e00-\u0e7f]"), 5),  # Thai
    (re.compile(r"[\u0e80-\u0eff]"), 6),  # Lao
    (re.compile(r"[\u1780-\u17ff]"), 6),  # Khmer
    (re.compile(r"[\u1000-\u109f]"), 8),  # Burmese
)


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
    """Words separated by spaces, with the scripts that use none (Chinese,
    Japanese, Thai, Lao, Khmer, Burmese) counted at a fixed number of characters
    a word."""
    spaced = _CJK_PUNCTUATION.sub(" ", text)
    unspaced = Fraction(0)
    for script, characters_per_word in _UNSPACED_SCRIPTS:
        unspaced += Fraction(len(script.findall(text)), characters_per_word)
        spaced = script.sub(" ", spaced)
    return len(spaced.split()) + math.ceil(unspaced)


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
