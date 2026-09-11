# -*- coding: utf-8 -*-
"""Persian text normalization.

Both the knowledge base and every incoming message pass through the exact same
pipeline, so the two are always compared on equal footing. The goal is to make
"كيفيت" and "کیفیت", "می‌خواهم" and "می خواهم", and "۱۲۳" and "123" collapse to
one canonical form.
"""
from __future__ import annotations

import re
import unicodedata

# Arabic letterforms that Persian writers mix in, mapped to Persian.
_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",  # Arabic yeh            → Persian yeh
        "ى": "ی",  # Alef maksura          → Persian yeh
        "ك": "ک",  # Arabic kaf            → Persian kaf
        "ة": "ه",  # Teh marbuta           → heh
        "ۀ": "ه",  # Heh with yeh above    → heh
        "أ": "ا",  # Alef with hamza above → alef
        "إ": "ا",  # Alef with hamza below → alef
        "آ": "ا",  # Alef with madda       → alef
        "ٱ": "ا",  # Alef wasla            → alef
        "ؤ": "و",  # Waw with hamza        → waw
        "ئ": "ی",  # Yeh with hamza        → yeh
        "ﻻ": "لا",
        "ﻷ": "لا",
        "ﻹ": "لا",
    }
)

# Persian (۰-۹), Arabic-Indic (٠-٩) and Eastern Arabic-Indic (۰-۹) digits.
_DIGIT_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

# Arabic diacritics: harakat, tanwin, sukun, shadda, superscript alef.
_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")

_TATWEEL = "\u0640"          # kashida stretching character
_ZWNJ = "\u200c"             # zero-width non-joiner (نیم‌فاصله)
_ZWJ = "\u200d"              # zero-width joiner
_BOM = "\ufeff"

# Anything that is not a letter, a digit or whitespace becomes a space.
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_UNDERSCORE = re.compile(r"_")

# Persian/Arabic combining marks that survive unicodedata normalization.
_HAS_LETTER = re.compile(r"[A-Za-z\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def normalize(text: str | None) -> str:
    """Return the canonical form of ``text`` used for indexing and matching.

    Pipeline: Unicode NFC → Arabic→Persian letters → digits to ASCII →
    diacritics and tatweel removed → ZWNJ/ZWJ collapsed to a space →
    punctuation and symbols dropped → lowercased → whitespace collapsed.
    """
    if not text:
        return ""

    t = unicodedata.normalize("NFC", str(text))
    t = t.replace(_BOM, " ").replace(_ZWJ, " ")
    t = t.translate(_CHAR_MAP)
    t = t.translate(_DIGIT_MAP)
    t = t.replace(_TATWEEL, "")
    t = _DIACRITICS.sub("", t)
    t = t.replace(_ZWNJ, " ")
    t = _NON_WORD.sub(" ", t)
    t = _UNDERSCORE.sub(" ", t)
    t = t.lower()
    return _WHITESPACE.sub(" ", t).strip()


def has_letters(text: str) -> bool:
    """True when ``text`` contains at least one letter (Latin or Persian)."""
    return bool(_HAS_LETTER.search(text))


def digits_to_persian(value: str | int) -> str:
    """Render a number with Persian digits (for the UI)."""
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
