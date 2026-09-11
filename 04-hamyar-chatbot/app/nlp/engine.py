# -*- coding: utf-8 -*-
"""Chat engine — retrieval plus a deterministic response policy.

The engine decides *how confident* a match is and what the visitor sees when
confidence is not high enough. It never guesses: below the medium threshold it
returns a controlled fallback, the closest topics as suggestions, and an offer
to reach a human agent.
"""
from __future__ import annotations

import random
import threading
import time
from typing import Mapping, Sequence

from app.models import Candidate, ChatReply, Confidence, FallbackReason, Faq, KbEntry

from .normalizer import normalize
from .retriever import TfidfRetriever
from .tokenizer import content_tokens

# Visitor-facing fallback copy. Kept short, calm and never apologetic twice.
EMPTY_MESSAGE_REPLY = (
    "پیام شما خالی بود. سؤالتان را بنویسید تا از دانشنامهٔ پشتیبانی برایتان "
    "پاسخ پیدا کنم."
)
NO_KNOWLEDGE_REPLY = (
    "الان به دانشنامهٔ پشتیبانی دسترسی ندارم. لطفاً چند لحظه بعد دوباره تلاش کنید "
    "یا درخواستتان را به کارشناس انسانی بسپارید."
)
LOW_CONFIDENCE_REPLY = (
    "پاسخ دقیقی برای این پرسش در دانشنامه پیدا نکردم، پس حدس نمی‌زنم. "
    "اگر یکی از موضوع‌های پیشنهادی زیر به کارتان می‌آید انتخاب کنید، یا درخواست "
    "خود را با یک کارشناس انسانی در میان بگذارید."
)

OUT_OF_DOMAIN_REPLY = (
    "این پرسش بیرون از حوزهٔ دانشنامهٔ پشتیبانی است، پس پاسخ حدسی نمی‌دهم. "
    "اگر منظورت یکی از موضوع‌های زیر است انتخابش کن، یا درخواستت را به کارشناس "
    "انسانی بسپار."
)


class ChatEngine:
    """Thread-safe retrieval engine with a confidence policy.

    The index is swapped atomically on :meth:`load`, so the admin panel can add
    or edit knowledge while visitors are chatting.
    """

    def __init__(
        self,
        high_confidence: float = 0.52,
        medium_confidence: float = 0.30,
        suggestion_floor: float = 0.12,
        max_suggestions: int = 3,
        evidence_floor: float = 0.45,
        char_support: float = 0.5,
    ) -> None:
        if medium_confidence > high_confidence:
            raise ValueError("medium_confidence must not exceed high_confidence")
        self.high_confidence = high_confidence
        self.medium_confidence = medium_confidence
        self.suggestion_floor = suggestion_floor
        self.max_suggestions = max_suggestions
        self.evidence_floor = evidence_floor
        self.char_support = char_support

        self._lock = threading.RLock()
        self._retriever: TfidfRetriever | None = None
        self._faqs: dict[int, Faq] = {}
        self._questions: list[str] = []
        self._loaded_at: float = 0.0

    # ------------------------------------------------------------- lifecycle
    def load(self, entries: Sequence[KbEntry], faqs: Mapping[int, Faq]) -> None:
        """Replace the knowledge index in one atomic swap."""
        retriever = TfidfRetriever(entries)
        questions = sorted({faq.question for faq in faqs.values()})
        with self._lock:
            self._retriever = retriever
            self._faqs = dict(faqs)
            self._questions = questions
            self._loaded_at = time.time()

    @property
    def ready(self) -> bool:
        """True when an index is loaded and non-empty."""
        with self._lock:
            return bool(self._retriever and self._retriever.ready)

    @property
    def size(self) -> int:
        """Number of indexed knowledge entries."""
        with self._lock:
            return len(self._retriever) if self._retriever else 0

    @property
    def faq_count(self) -> int:
        """Number of distinct FAQs behind the index."""
        with self._lock:
            return len(self._faqs)

    def sample_questions(self, limit: int = 6) -> list[str]:
        """Return a random sample of questions for the empty state."""
        with self._lock:
            pool = list(self._questions)
        if len(pool) <= limit:
            return pool
        return random.sample(pool, limit)

    def suggest(self, text: str, limit: int = 6) -> list[str]:
        """Type-ahead suggestions: questions containing the typed text."""
        normalized = normalize(text)
        if not normalized:
            return self.sample_questions(limit)
        with self._lock:
            pool = list(self._questions)
        tokens = content_tokens(normalized)
        hits = [q for q in pool if normalized in normalize(q)]
        if not hits and tokens:
            hits = [q for q in pool if any(t in normalize(q) for t in tokens)]
        return hits[:limit]

    def stats(self) -> dict[str, object]:
        """Introspection for /health and the admin dashboard."""
        return {
            "ready": self.ready,
            "entries": self.size,
            "faqs": self.faq_count,
            "high_confidence": self.high_confidence,
            "medium_confidence": self.medium_confidence,
            "evidence_floor": self.evidence_floor,
        }

    # ---------------------------------------------------------------- reply
    def reply(self, message: str) -> ChatReply:
        """Answer one visitor message according to the confidence policy."""
        started = time.perf_counter()

        normalized = normalize(message)
        if not normalized or not content_tokens(normalized):
            return self._result(
                EMPTY_MESSAGE_REPLY,
                matched=False,
                confidence=Confidence.LOW,
                score=0.0,
                reason=FallbackReason.EMPTY,
                started=started,
            )

        if not self.ready:
            return self._result(
                NO_KNOWLEDGE_REPLY,
                matched=False,
                confidence=Confidence.LOW,
                score=0.0,
                reason=FallbackReason.NO_KNOWLEDGE,
                started=started,
            )

        with self._lock:
            retriever = self._retriever
            faqs = dict(self._faqs)

        assert retriever is not None
        candidates = retriever.search(normalized, top_k=max(self.max_suggestions + 2, 5))
        candidates = self._annotate(candidates, faqs)

        if not candidates:
            return self._result(
                NO_KNOWLEDGE_REPLY,
                matched=False,
                confidence=Confidence.LOW,
                score=0.0,
                reason=FallbackReason.NO_KNOWLEDGE,
                started=started,
            )

        best = candidates[0]
        alternatives = self._alternatives(candidates, best.faq_id)
        faq = faqs.get(best.faq_id)

        # A high similarity score is not enough on its own: TF-IDF ignores
        # words it has never seen, so a mostly-unknown question can still score
        # well on a single shared word. Every match must be justified by either
        # vocabulary coverage or clear orthographic overlap.
        if faq is not None and not self._is_supported(normalized, best, retriever, faq):
            return self._result(
                OUT_OF_DOMAIN_REPLY,
                matched=False,
                confidence=Confidence.LOW,
                score=best.score,
                suggestions=alternatives,
                reason=FallbackReason.OUT_OF_DOMAIN,
                started=started,
            )

        if best.score >= self.high_confidence and faq is not None:
            return self._result(
                faq.answer,
                matched=True,
                confidence=Confidence.HIGH,
                score=best.score,
                faq=faq,
                matched_text=best.text,
                suggestions=alternatives,
                started=started,
            )

        if best.score >= self.medium_confidence and faq is not None:
            return self._result(
                faq.answer,
                matched=True,
                confidence=Confidence.MEDIUM,
                score=best.score,
                faq=faq,
                matched_text=best.text,
                suggestions=alternatives,
                reason=FallbackReason.MEDIUM,
                started=started,
            )

        return self._result(
            LOW_CONFIDENCE_REPLY,
            matched=False,
            confidence=Confidence.LOW,
            score=best.score,
            suggestions=alternatives,
            reason=FallbackReason.LOW,
            started=started,
        )

    # -------------------------------------------------------------- helpers
    def _evidence(
        self,
        message: str,
        best: Candidate,
        retriever: TfidfRetriever,
        faq: Faq | None = None,
    ) -> float:
        """Share of the question's information that the matched topic explains.

        Every content token carries an IDF weight; a token the corpus has never
        seen is treated as maximally rare. The score is the matched weight over
        the total weight, so a question built from unknown words cannot look
        confident just because one common word happens to overlap.

        Coverage is measured against the whole topic — every phrasing of the
        entry together with the wording of its answer — because a visitor who
        asks «وجه سفارشم برنگشته» is on topic even though none of those exact
        words appear in the entry that matched.
        """
        tokens = content_tokens(message)
        if not tokens:
            return 0.0
        weights = retriever.idf
        unknown_weight = retriever.max_idf

        topic_tokens = set(retriever.topic_tokens(best.faq_id))
        if faq is not None:
            topic_tokens.update(content_tokens(faq.question))
            topic_tokens.update(content_tokens(faq.answer))

        total = 0.0
        matched = 0.0
        for token in tokens:
            weight = weights.get(token, unknown_weight)
            total += weight
            if token in topic_tokens:
                matched += weight
        return matched / total if total else 0.0

    def _is_supported(
        self,
        message: str,
        best: Candidate,
        retriever: TfidfRetriever,
        faq: Faq | None = None,
    ) -> bool:
        """Decide whether a candidate match is trustworthy.

        Two independent signals are accepted:

        * **information coverage** — the matched entry explains most of the
          IDF weight of the question, so the shared terms really are the topic;
          or
        * **orthographic support** — coverage is poor, but the character
          n-grams line up, which is what a typo or a colloquial ending looks
          like (``سفارشمو`` vs ``سفارشم``).

        Anything else is treated as out of domain and gets a controlled
        fallback instead of a possibly wrong answer.
        """
        if self._evidence(message, best, retriever, faq) >= self.evidence_floor:
            return True
        return best.char_score >= self.char_support

    def _annotate(
        self, candidates: Sequence[Candidate], faqs: Mapping[int, Faq]
    ) -> list[Candidate]:
        """Attach the owning category to each candidate and drop duplicates.

        Only the strongest hit per FAQ is kept, so suggestions never repeat the
        same topic twice.
        """
        best_per_faq: dict[int, Candidate] = {}
        for candidate in candidates:
            faq = faqs.get(candidate.faq_id)
            if faq is not None:
                candidate.category = faq.category
            current = best_per_faq.get(candidate.faq_id)
            if current is None or candidate.score > current.score:
                best_per_faq[candidate.faq_id] = candidate
        return sorted(best_per_faq.values(), key=lambda c: c.score, reverse=True)

    def _alternatives(
        self, candidates: Sequence[Candidate], exclude_faq_id: int | None
    ) -> list[Candidate]:
        """Pick the closest topics that are worth showing as suggestions."""
        picked: list[Candidate] = []
        for candidate in candidates:
            if candidate.faq_id == exclude_faq_id:
                continue
            if candidate.score < self.suggestion_floor:
                continue
            picked.append(candidate)
            if len(picked) >= self.max_suggestions:
                break
        return picked

    @staticmethod
    def _result(
        answer: str,
        *,
        matched: bool,
        confidence: Confidence,
        score: float,
        started: float,
        faq: Faq | None = None,
        matched_text: str | None = None,
        suggestions: Sequence[Candidate] = (),
        reason: FallbackReason | None = None,
    ) -> ChatReply:
        """Build a ChatReply with the measured latency."""
        return ChatReply(
            answer=answer,
            matched=matched,
            confidence=confidence,
            score=float(score),
            faq_id=faq.id if faq else None,
            category=faq.category if faq else None,
            matched_question=matched_text or (faq.question if faq else None),
            suggestions=list(suggestions),
            fallback_reason=reason,
            latency_ms=int((time.perf_counter() - started) * 1000),
            handoff_available=not matched or confidence is not Confidence.HIGH,
        )
