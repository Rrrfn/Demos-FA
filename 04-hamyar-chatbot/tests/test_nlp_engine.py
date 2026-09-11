# -*- coding: utf-8 -*-
"""Retrieval and response policy — the quality contract of the assistant."""
from __future__ import annotations

import pytest

from app.models import Confidence, FallbackReason
from app.nlp import ChatEngine


class TestExactAndParaphrasedMatches:
    """Questions the knowledge base must answer."""

    def test_exact_question(self, engine):
        reply = engine.reply("هزینه ارسال چقدر است؟")
        assert reply.matched is True
        assert reply.confidence is Confidence.HIGH
        assert "۵۰۰ هزار" in reply.answer or "ارسال" in reply.answer
        assert reply.faq_id is not None

    @pytest.mark.parametrize(
        "question",
        [
            "چند روزه به دستم می‌رسه؟",
            "زمان تحویل سفارش چقدره؟",
            "سفارش من کِی می‌رسد؟",
        ],
    )
    def test_colloquial_variants(self, engine, question):
        """Variant phrasings must hit the shipping-time entry."""
        reply = engine.reply(question)
        assert reply.matched is True
        assert reply.score >= engine.medium_confidence
        assert "روز کاری" in reply.answer

    def test_typo_tolerance(self, engine):
        """Character n-grams absorb small spelling differences."""
        reply = engine.reply("شرایط مرجوعی کالا چیه؟")
        assert reply.matched is True
        assert "۷ روز" in reply.answer

    def test_arabic_typing_is_normalized(self, engine):
        """A visitor typing with an Arabic keyboard still gets an answer."""
        reply = engine.reply("مبلغ از حسابم كسر شد ولي سفارش ثبت نشد")
        assert reply.matched is True
        assert "رزرو" in reply.answer or "تراکنش" in reply.answer

    def test_confidence_bands_are_ordered(self, engine):
        assert engine.high_confidence > engine.medium_confidence > engine.suggestion_floor


class TestControlsAndFallback:
    """The engine must never answer when it is not sure."""

    def test_gibberish_falls_back(self, engine):
        reply = engine.reply("qwzxv bbnn mmmasdf")
        assert reply.matched is False
        assert reply.confidence is Confidence.LOW
        assert reply.fallback_reason in (FallbackReason.LOW, FallbackReason.NO_KNOWLEDGE)
        assert reply.faq_id is None

    @pytest.mark.parametrize(
        "question",
        [
            "قیمت بیت‌کوین امروز چنده؟",
            "برای من یک فنجان قهوه سفارش بده",
            "هوای تهران فردا چطور است؟",
            "یک بلیط هواپیما برای مشهد می‌خواهم",
            "پایتخت استرالیا کجاست؟",
            "برای مهاجرت به کانادا چی لازمه؟",
            "بهترین گوشی موبایل چیه؟",
            "بازی فوتبال دیشب چند چند شد؟",
            "قیمت دلار امروز چند شد؟",
            "نحوه پخت قرمه سبزی",
            "یه شعر از حافظ برام بنویس",
            "می‌خوام یه برنامه پایتون بنویسم",
        ],
    )
    def test_out_of_domain_questions_are_controlled(self, engine, question):
        """A single shared word must not turn an unrelated question into a match.

        These questions contain one tempting keyword («قیمت», «سفارش») but the
        rest of the words are unknown to the knowledge base, so answering would
        be a guess.
        """
        reply = engine.reply(question)
        assert reply.matched is False
        assert reply.faq_id is None
        assert reply.answer  # never an empty string
        assert "حدس نمی‌زنم" in reply.answer or "کارشناس" in reply.answer

    def test_gate_reports_its_reason(self, engine):
        reply = engine.reply("قیمت بیت‌کوین امروز چنده؟")
        assert reply.fallback_reason is FallbackReason.OUT_OF_DOMAIN

    @pytest.mark.parametrize(
        "question",
        [
            "سفارشمو گم کردم چیکار کنم؟",          # colloquial spelling
            "هزینه پست به شیراز چقدره؟",
            "شماره پیگیری سفارشو کجا بزنم",         # glued «را»
            "چطور رمزم رو عوض کنم؟",              # change-password entry
            "پسورد یادم رفته چیکار کنم؟",
            "سلام، پولمو پس بدید",                  # refund entry
            "سفارشمو لغو کنید لطفا",
            "می‌شه فاکتور برام بفرستید",
            "کد رهگیریمو گم کردم چیکار کنم",
            "گارانتی محصولات چقدره؟",              # «محصولات» vs «کالاها»
            "چطور وجه سفارشم برگشت داده میشه؟",      # «برگشت» vs «بازگشت»
        ],
    )
    def test_gate_keeps_real_questions_working(self, engine, question):
        """The out-of-domain gate must not block genuine, colloquial questions."""
        reply = engine.reply(question)
        assert reply.matched is True
        assert reply.fallback_reason is not FallbackReason.OUT_OF_DOMAIN

    @pytest.mark.parametrize(
        "question",
        [
            "بسته‌بندی هدیه دارید؟",                # no such entry in the knowledge base
            "بعد از خرید چطور از وضعیت سفارش باخبر بشم؟",
        ],
    )
    def test_uncovered_topic_falls_back_with_suggestions(self, engine, question):
        """A topic the knowledge base does not cover must never be guessed at.

        The visitor still gets a way forward: the closest topics as suggestions
        plus the offer of a human agent.
        """
        reply = engine.reply(question)
        assert reply.matched is False
        assert reply.answer
        assert reply.handoff_available is True

    def test_empty_message(self, engine):
        reply = engine.reply("   ")
        assert reply.matched is False
        assert reply.fallback_reason is FallbackReason.EMPTY

    def test_empty_knowledge_base(self):
        """With no knowledge loaded the engine degrades explicitly."""
        empty = ChatEngine()
        reply = empty.reply("هزینه ارسال چقدر است؟")
        assert empty.ready is False
        assert reply.matched is False
        assert reply.fallback_reason is FallbackReason.NO_KNOWLEDGE


class TestEvidenceGate:
    """Similarity alone is not evidence — the gate needs a second signal.

    TF-IDF drops words it has never seen, so an unrelated question can score
    highly on one shared common word («قیمت», «لازمه»). These tests pin the
    behaviour that stops that from becoming an answer.
    """

    def test_unknown_topic_sharing_one_keyword_is_rejected(self, engine):
        reply = engine.reply("قیمت بیت‌کوین امروز چنده؟")
        assert reply.matched is False
        assert reply.fallback_reason is FallbackReason.OUT_OF_DOMAIN

    def test_shared_phrase_frame_is_not_evidence(self, engine):
        """«برای ... چی لازمه؟» is a frame, not a topic."""
        reply = engine.reply("برای مهاجرت به کانادا چی لازمه؟")
        assert reply.matched is False

    def test_question_particles_do_not_carry_meaning(self, engine):
        """Pure question words must not count towards coverage."""
        from app.nlp.tokenizer import content_tokens

        for particle in ("چی", "چیه", "چه", "آیا"):
            assert particle not in content_tokens(f"{particle} خبر داری")

    def test_evidence_is_reported_and_bounded(self, engine):
        retriever = engine._retriever
        question = "هزینه ارسال چقدره؟"
        best = retriever.search(question, top_k=1)[0]
        evidence = engine._evidence(
            question, best, retriever, engine._faqs.get(best.faq_id)
        )
        assert 0.0 <= evidence <= 1.0
        assert evidence >= engine.evidence_floor

    def test_coverage_is_measured_against_the_whole_topic(self, engine):
        """A different phrasing of the same entry still counts as on-topic."""
        retriever = engine._retriever
        question = "گارانتی محصولات چقدره؟"
        best = retriever.search(question, top_k=1)[0]
        tokens = retriever.topic_tokens(best.faq_id)
        assert "گارانتی" in tokens


class TestSuggestions:
    """Suggestions are the recovery path of a controlled fallback."""

    def test_suggestions_are_distinct_and_capped(self, engine):
        reply = engine.reply("هزینه ارسال چقدر است؟")
        ids = [item.faq_id for item in reply.suggestions]
        assert len(ids) == len(set(ids))
        assert len(ids) <= engine.max_suggestions

    def test_type_ahead(self, engine):
        suggestions = engine.suggest("مرجوع")
        assert suggestions
        assert all("مرجوع" in item for item in suggestions)

    def test_type_ahead_without_input_shows_a_sample(self, engine):
        sample = engine.suggest("")
        assert sample
        assert len(sample) <= 6

    def test_sample_questions(self, engine):
        sample = engine.sample_questions(6)
        assert len(sample) == 6
        assert all(isinstance(item, str) for item in sample)

    def test_engine_stats(self, engine):
        stats = engine.stats()
        assert stats["ready"] is True
        assert stats["entries"] >= stats["faqs"] > 0


class TestThresholdConfiguration:
    """Misconfiguration must fail loudly instead of silently degrading."""

    def test_inverted_thresholds_raise(self):
        with pytest.raises(ValueError):
            ChatEngine(high_confidence=0.2, medium_confidence=0.8)
