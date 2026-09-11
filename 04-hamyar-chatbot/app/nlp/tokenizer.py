# -*- coding: utf-8 -*-
"""Tokenization for retrieval.

The stopword list is deliberately *conservative*: on a FAQ corpus, question
words like «چطور» or «کِی» are highly discriminative, so removing them would
hurt retrieval. Only pure function words (prepositions, conjunctions, copulas)
are dropped; IDF weighting handles the rest.
"""
from __future__ import annotations

from .normalizer import has_letters, normalize

# Function words with almost no discriminative power in a support corpus.
STOPWORDS: frozenset[str] = frozenset(
    {
        "از", "به", "با", "بی", "در", "که", "را", "و", "این", "آن", "برای",
        "است", "هست", "نیست", "نیز", "یک", "تا", "هم", "بر", "می", "های",
        "ها", "ش", "شد", "شده", "بود", "بوده", "کرد", "شود", "بشه",
        # Colloquial copulas and light verbs. These appear in almost every
        # spoken question, so leaving them in a short query would drown out the
        # one or two words that actually carry the topic.
        "میشه", "نمیشه", "میشد", "میشن", "میشین", "باشه", "داره", "دارم",
        "دارید", "دارن", "داده", "دادن", "کنم", "کنه", "کنید", "کنن",
        "کردم", "کرده", "کردن", "بدم", "بده", "بدید", "بگیرم", "بگیره",
        "بخوام", "نمیدونم", "نمیشه", "رو", "دیگه", "الان", "فقط",
        # Question particles. «برای گارانتی چی لازمه؟» and «برای مهاجرت چی
        # لازمه؟» share a frame but not a topic, so the frame must not count as
        # evidence for either of them.
        "چی", "چیه", "چه", "آیا", "برام", "برات", "براش", "بهم", "بهش",
        "the", "and", "for", "you", "are", "with", "this", "that", "what",
        "your", "can", "how", "does", "did", "was", "were", "from", "have",
    }
)

# Tokens that are meaningful even at two characters.
_MIN_LENGTH = 2

# Plural and possessive suffixes. Colloquial support questions switch between
# «محصولات»، «محصول‌ها» and «محصول» freely for the same thing, so the index and
# the query are reduced to a common form. Only suffixes that are unambiguous on
# a token of at least three letters are stripped; this is deliberately shallow,
# not a full stemmer.
_SUFFIXES: tuple[str, ...] = (
    "هایی", "های", "ها", "ات", "ان",
)


# Support-domain synonym groups. Persian support questions use several names
# for the same concept («بازگشت» و «برگشت»، «پول» و «مبلغ» و «وجه»). Mapping them
# to one canonical token keeps the index consistent without a thesaurus.
_SYNONYMS: dict[str, str] = {
    "بازگشت": "برگشت",
    "بازگشتن": "برگشت",
    "برگرداندن": "برگشت",
    "برگردوندن": "برگشت",
    "برمیگردد": "برگشت",
    "برمیگرده": "برگشت",
    "ضمانت": "گارانتی",
    "پول": "وجه",
    "مبلغ": "وجه",
    "مرجوع": "مرجوعی",
    "رهگیری": "پیگیری",
    "رهگیر": "پیگیر",
    "پست": "ارسال",
    "بفرستید": "ارسال",
    "فرستادن": "ارسال",
    "بفرستم": "ارسال",
    "برگرداند": "برگشت",
}


def stem(token: str) -> str:
    """Reduce a token to a shallow common form.

    Purely mechanical and deterministic: the same rule is applied to the
    corpus and to the visitor's question, so TF-IDF stays consistent.
    """
    for suffix in _SUFFIXES:
        if len(token) - len(suffix) >= 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    # Spoken Persian glues the object marker «را» onto the word: «سفارشو کجا
    # بزنم». Only a long token is trimmed, so ordinary words ending in «و»
    # (تلفظ، بازو، پالتو) are left untouched.
    if len(token) >= 5 and token.endswith("و"):
        return token[:-1]
    return token


def tokenize(text: str | None) -> list[str]:
    """Normalize then split on whitespace."""
    return normalize(text).split()


def content_tokens(text: str | None) -> list[str]:
    """Return normalized tokens suitable for TF-IDF indexing.

    A token is kept when it is at least two characters long, is not a
    stopword, and contains at least one letter — which drops stray numbers and
    symbols that would otherwise add noise to the vector space.
    """
    tokens = tokenize(text)
    result: list[str] = []
    for token in tokens:
        if len(token) < _MIN_LENGTH or token in STOPWORDS:
            continue
        if not has_letters(token):
            continue
        result.append(canonical(stem(token)))
    return result


def canonical(token: str) -> str:
    """Map a token onto its canonical support-domain spelling."""
    return _SYNONYMS.get(token, token)


def token_count(text: str | None) -> int:
    """Number of content tokens, used for query-length heuristics."""
    return len(content_tokens(text))
