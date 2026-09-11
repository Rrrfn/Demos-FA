# -*- coding: utf-8 -*-
"""Retrieval index.

TF-IDF on words alone is brittle for short, colloquial Persian questions
("چند روزه می‌رسه؟"), because a single missing word can zero out the overlap.
The index therefore blends two complementary views of the same text:

* **word TF-IDF**       — what the visitor is talking about
* **character n-grams** — how it is spelled, tolerant of typos, spacing and
  inflection

Both matrices are L2-normalised, so cosine similarity is directly comparable
and the blend is a simple weighted sum.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import Candidate, KbEntry

from .normalizer import normalize
from .tokenizer import content_tokens

WORD_WEIGHT = 0.65
CHAR_WEIGHT = 0.35


class TfidfRetriever:
    """Immutable, thread-safe retrieval index over knowledge-base entries."""

    def __init__(
        self,
        entries: Sequence[KbEntry],
        word_weight: float = WORD_WEIGHT,
        char_weight: float = CHAR_WEIGHT,
    ) -> None:
        self.word_weight = word_weight
        self.char_weight = char_weight
        self._entries: list[KbEntry] = list(entries)
        self._texts = [normalize(entry.text) for entry in self._entries]

        # Vocabulary of each topic as a whole, not of one phrasing of it. The
        # response policy measures coverage against this set, so a visitor who
        # phrases a question differently is still recognised as talking about
        # the same subject.
        self._topic_tokens: dict[int, set[str]] = {}
        for entry, text in zip(self._entries, self._texts):
            self._topic_tokens.setdefault(entry.faq_id, set()).update(content_tokens(text))

        usable = [text for text in self._texts if text.strip()]
        self._word_vectorizer: TfidfVectorizer | None = None
        self._char_vectorizer: TfidfVectorizer | None = None
        self._word_matrix = None
        self._char_matrix = None

        if not usable:
            return

        self._word_vectorizer = TfidfVectorizer(
            analyzer="word",
            tokenizer=content_tokens,
            preprocessor=normalize,
            token_pattern=None,
            sublinear_tf=True,
            norm="l2",
        )
        self._word_matrix = self._word_vectorizer.fit_transform(self._texts)

        # Character n-grams are computed over the content words only. Run over
        # the raw sentence they would score a shared *frame* — «برای ... چی
        # لازمه؟» — as if it were shared meaning, which is exactly how an
        # unrelated question could scrape past the confidence gate.
        self._char_texts = [" ".join(content_tokens(text)) for text in self._texts]
        self._char_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            preprocessor=normalize,
            lowercase=False,
            sublinear_tf=True,
            norm="l2",
        )
        self._char_matrix = self._char_vectorizer.fit_transform(self._char_texts)

    # ------------------------------------------------------------------ info
    def __len__(self) -> int:
        """Number of indexed entries."""
        return len(self._entries)

    @property
    def ready(self) -> bool:
        """True when the index holds at least one usable entry."""
        return self._word_vectorizer is not None and len(self._entries) > 0

    @property
    def idf(self) -> dict[str, float]:
        """Inverse document frequency of every known token.

        The response policy uses these weights to tell an informative word such
        as «بیت‌کوین» from a filler word such as «تهران»; TF-IDF similarity on
        its own cannot, because out-of-vocabulary terms simply vanish from the
        vector and common terms survive.
        """
        if self._word_vectorizer is None:
            return {}
        vocabulary = self._word_vectorizer.vocabulary_
        values = self._word_vectorizer.idf_
        return {token: float(values[index]) for token, index in vocabulary.items()}

    @property
    def max_idf(self) -> float:
        """Weight assigned to a word the corpus has never seen.

        An unknown word is maximally rare by definition, so it receives the
        corpus maximum. That makes unmatched, unknown words dominate the
        evidence denominator instead of silently disappearing.
        """
        weights = self.idf
        return max(weights.values()) if weights else 1.0

    def topic_tokens(self, faq_id: int) -> set[str]:
        """Every content token used by any phrasing of one knowledge entry."""
        return self._topic_tokens.get(faq_id, set())

    # ---------------------------------------------------------------- search
    def search(self, query: str, top_k: int = 5) -> list[Candidate]:
        """Return the best-scoring entries for ``query``, highest first.

        An empty or unindexable query returns an empty list rather than a
        zero-score guess, which keeps the caller's fallback logic honest.
        """
        if not self.ready:
            return []

        normalized = normalize(query)
        if not normalized:
            return []

        word_scores = self._similarity(self._word_vectorizer, self._word_matrix, normalized)
        char_query = " ".join(content_tokens(normalized))
        char_scores = self._similarity(self._char_vectorizer, self._char_matrix, char_query)
        blended = self.word_weight * word_scores + self.char_weight * char_scores

        limit = max(1, min(top_k, len(self._entries)))
        order = np.argsort(-blended)[:limit]

        candidates: list[Candidate] = []
        for index in order:
            score = float(blended[index])
            if score <= 0:
                continue
            entry = self._entries[int(index)]
            candidates.append(
                Candidate(
                    faq_id=entry.faq_id,
                    text=entry.text,
                    score=score,
                    word_score=float(word_scores[index]),
                    char_score=float(char_scores[index]),
                    is_primary=entry.is_primary,
                )
            )
        return candidates

    @staticmethod
    def _similarity(vectorizer, matrix, text: str) -> np.ndarray:
        """Cosine similarity of one text against the whole index."""
        if vectorizer is None or matrix is None:
            return np.zeros(0)
        vector = vectorizer.transform([text])
        if vector.nnz == 0:
            return np.zeros(matrix.shape[0])
        return cosine_similarity(vector, matrix).ravel()
