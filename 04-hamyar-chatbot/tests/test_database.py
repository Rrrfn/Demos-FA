# -*- coding: utf-8 -*-
"""Database layer: schema, FAQ CRUD, logging and analytics."""
from __future__ import annotations

from app.database import (
    AnalyticsRepository,
    ConversationRepository,
    FaqRepository,
    HandoffRepository,
    session,
)


def test_schema_and_seed_are_created(ctx, faq_count):
    """The first start creates the schema and seeds the knowledge base."""
    assert faq_count >= 40


def test_seed_is_idempotent(ctx):
    """Re-initialising an existing database must not duplicate entries."""
    from app.database import initialize_database

    with session() as conn:
        before = FaqRepository(conn).count()
    initialize_database()
    with session() as conn:
        after = FaqRepository(conn).count()
    assert before == after


class TestFaqRepository:
    """CRUD, search and variant handling."""

    def test_create_get_update_delete(self, ctx):
        with session() as conn:
            repo = FaqRepository(conn)
            faq_id = repo.create(
                "پرسش آزمایشی؟", "پاسخ آزمایشی", "تست", ["عبارت جایگزین"]
            )
            created = repo.get(faq_id)
            assert created is not None
            assert created.variants == ("عبارت جایگزین",)

            assert repo.update(faq_id, "پرسش ویرایش‌شده؟", "پاسخ ویرایش‌شده", "تست۲", [])
            updated = repo.get(faq_id)
            assert updated.question == "پرسش ویرایش‌شده؟"
            assert updated.category == "تست۲"
            assert updated.variants == ()

            assert repo.delete(faq_id) is True
            assert repo.get(faq_id) is None
            assert repo.delete(faq_id) is False

    def test_variants_are_deduplicated(self, ctx):
        with session() as conn:
            repo = FaqRepository(conn)
            faq_id = repo.create("پ؟", "پ", "تست", ["یک", " یک ", "دو", "", "دو"])
            assert repo.variants(faq_id) == ["یک", "دو"]

    def test_delete_cascades_to_variants(self, ctx):
        with session() as conn:
            repo = FaqRepository(conn)
            faq_id = repo.create("پ؟", "پ", "تست", ["یک"])
            repo.delete(faq_id)
            remaining = conn.execute(
                "SELECT COUNT(*) FROM faq_variant WHERE faq_id = ?", (faq_id,)
            ).fetchone()[0]
            assert remaining == 0

    def test_search_matches_question_answer_and_variants(self, ctx):
        with session() as conn:
            repo = FaqRepository(conn)
            repo.create("پرسش مخصوص جست‌وجو؟", "پاسخ", "تست", ["واژهٔ کمیاب"])
            assert repo.count(search="مخصوص") == 1
            assert repo.count(search="واژهٔ کمیاب") == 1
            assert repo.count(search="واژهٔ ناموجود") == 0

    def test_filter_by_category_and_pagination(self, ctx):
        with session() as conn:
            repo = FaqRepository(conn)
            first_page = repo.list(limit=5)
            second_page = repo.list(limit=5, offset=5)
            assert len(first_page) == 5
            assert {f.id for f in first_page}.isdisjoint({f.id for f in second_page})
            assert repo.count(category="پرداخت و صورتحساب") > 0
            assert repo.count(category="دستهٔ ناموجود") == 0

    def test_categories_are_counted(self, ctx):
        with session() as conn:
            categories = FaqRepository(conn).categories()
        assert categories
        assert all(item["count"] > 0 and item["category"] for item in categories)

    def test_kb_entries_include_primary_and_variants(self, ctx):
        with session() as conn:
            entries = FaqRepository(conn).kb_entries()
        assert len(entries) > 40
        assert any(entry.is_primary for entry in entries)
        assert any(not entry.is_primary for entry in entries)


class TestConversationRepository:
    """Logging, transcripts, feedback and unanswered aggregation."""

    @staticmethod
    def _log(conn, text, answered=True, score=0.8, session_id="s-123456"):
        return ConversationRepository(conn).log(
            session_id=session_id,
            user_text=text,
            matched_faq_id=1 if answered else None,
            matched_text="پرسش مرجع" if answered else None,
            score=score,
            confidence="high" if answered else "low",
            answered=answered,
            category="تست",
            latency_ms=12,
        )

    def test_log_and_read_back(self, ctx):
        with session() as conn:
            conversation_id = self._log(conn, "سلام")
            turn = ConversationRepository(conn).get(conversation_id)
        assert turn is not None
        assert turn.user_text == "سلام"
        assert turn.answered is True

    def test_session_transcript_is_ordered(self, ctx):
        with session() as conn:
            repo = ConversationRepository(conn)
            self._log(conn, "پیام یک", session_id="s-abcdef")
            self._log(conn, "پیام دو", session_id="s-abcdef")
            self._log(conn, "پیام دیگر", session_id="s-zzzzzz")
            transcript = repo.by_session("s-abcdef")
        assert [t.user_text for t in transcript] == ["پیام یک", "پیام دو"]

    def test_filters_and_counts(self, ctx):
        with session() as conn:
            repo = ConversationRepository(conn)
            self._log(conn, "پرسش پاسخ‌یافته")
            self._log(conn, "پرسش بی‌پاسخ", answered=False, score=0.05)
            assert repo.count() >= 2
            assert repo.count(status="answered") >= 1
            assert repo.count(status="unanswered") >= 1
            assert any("بی‌پاسخ" in t.user_text for t in repo.list(status="unanswered"))
            assert repo.count(search="پاسخ‌یافته") >= 1

    def test_feedback_roundtrip(self, ctx):
        with session() as conn:
            repo = ConversationRepository(conn)
            conversation_id = self._log(conn, "بازخورد")
            assert repo.set_feedback(conversation_id, "up") is True
            assert repo.get(conversation_id).feedback == "up"
            assert repo.set_feedback(conversation_id, None) is True
            assert repo.get(conversation_id).feedback is None
            assert repo.set_feedback(999999, "up") is False

    def test_top_unanswered_groups_repeats(self, ctx):
        with session() as conn:
            repo = ConversationRepository(conn)
            for _ in range(3):
                self._log(conn, "پرسش تکرارشوندهٔ بی‌پاسخ", answered=False, score=0.1)
            top = repo.top_unanswered()
        assert top[0]["message"] == "پرسش تکرارشوندهٔ بی‌پاسخ"
        assert top[0]["count"] >= 3


class TestHandoffAndAnalytics:
    """Handoff tickets and the dashboard aggregate."""

    def test_handoff_create_and_list(self, ctx):
        with session() as conn:
            repo = HandoffRepository(conn)
            ticket_id = repo.create("s-123456", "دلیل", "آخرین پرسش")
            handoffs = repo.list()
            assert repo.count() >= 1
        assert handoffs[0].id == ticket_id
        assert handoffs[0].to_dict()["ticket"] == f"HM-{ticket_id:05d}"

    def test_overview_aggregates(self, ctx):
        with session() as conn:
            conversations = ConversationRepository(conn)
            conversations.log(
                session_id="s-aaaaaa", user_text="پرسش", matched_faq_id=1,
                matched_text="مرجع", score=0.9, confidence="high",
                answered=True, category="تست", latency_ms=20,
            )
            conversations.log(
                session_id="s-aaaaaa", user_text="بی‌پاسخ", matched_faq_id=None,
                matched_text=None, score=0.02, confidence="low",
                answered=False, category=None, latency_ms=8,
            )
            overview = AnalyticsRepository(conn).overview(days=7)

        assert overview["turns"] >= 2
        assert overview["answered"] >= 1
        assert overview["unanswered"] >= 1
        assert 0 <= overview["match_rate"] <= 100
        assert len(overview["daily"]) == 7
        assert overview["confidence"]["high"] >= 1
        assert overview["top_unanswered"]
        assert overview["avg_latency_ms"] >= 0
