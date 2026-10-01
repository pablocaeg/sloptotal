"""Languages in the multilingual evaluation, and how to cut samples in each.

Scripts without spaces between words (Chinese, Japanese) are cut by characters;
the character budget gives roughly the same amount of text as CHUNK_WORDS.
"""

CHUNK_WORDS = 220
CHUNK_CHARS_CJK = 420
MIN_WORDS = 120
MIN_CHARS_CJK = 240

# code: (English name, cut by characters)
LANGUAGES = {
    "es": ("Spanish", False),
    "fr": ("French", False),
    "de": ("German", False),
    "pt": ("Portuguese", False),
    "it": ("Italian", False),
    "nl": ("Dutch", False),
    "pl": ("Polish", False),
    "ru": ("Russian", False),
    "tr": ("Turkish", False),
    "ar": ("Arabic", False),
    "hi": ("Hindi", False),
    "zh": ("Chinese", True),
    "ja": ("Japanese", True),
    "ko": ("Korean", False),
}


def is_cjk(lang: str) -> bool:
    return LANGUAGES[lang][1]


def cut(text: str, lang: str) -> str | None:
    """A sample of the standard length, or None if the text is too short."""
    text = " ".join(text.split())
    if is_cjk(lang):
        if len(text) < MIN_CHARS_CJK:
            return None
        return text[:CHUNK_CHARS_CJK]
    words = text.split()
    if len(words) < MIN_WORDS:
        return None
    return " ".join(words[:CHUNK_WORDS])
