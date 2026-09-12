# -*- coding: utf-8 -*-
"""آزمون‌های خط لولهٔ جمع‌آوری — انزوای خطا، تکرار و صداقت داده.

دو وعدهٔ محصول اینجاست: «شکست یک منبع کل سیستم را نمی‌خواباند» و «اگر
داده‌ای نبود، آگهی جعلی ساخته نمی‌شود». هر دو باید ساختاراً قفل شوند.
"""
from __future__ import annotations

from dataclasses import replace

from karino.core.text import fa_number
from karino.pipeline.normalize import normalize
from karino.services.ingest import (known_sources, rescore_job, run_ingest,
                                    score_pending)
from karino.storage import activity, jobs as jobs_repo
from karino.storage import scores as scores_repo, sources as sources_repo

from .fakes import FakeSource, raw_job


def has_latin_digit(text: str) -> bool:
    return any(ch.isdigit() and ch.isascii() for ch in text)


#: عنوان‌های واقعاً متفاوت — عمداً فقط با یک عدد فرق نمی‌کنند، چون
#: حذف تکراری تقریبی توکن‌های تک‌حرفی را نادیده می‌گیرد.
_TITLES = (
    "توسعه‌دهندهٔ پایتون و Flask",
    "کارشناس تحلیل داده با pandas",
    "مهندس اتوماسیون و وب‌اسکرپینگ",
    "توسعه‌دهندهٔ ربات تلگرام",
    "کارشناس یادگیری ماشین",
)


def _source(key: str, count: int = 2, **overrides) -> FakeSource:
    overrides.setdefault("company", f"شرکت {key}")
    return FakeSource(key, [
        raw_job(source=key, index=i, title=_TITLES[(i - 1) % len(_TITLES)], **overrides)
        for i in range(1, count + 1)])


# ---------------------------------------------------------------- مسیر موفق


def test_ingest_stores_and_scores_new_jobs(db, settings):
    stats = run_ingest(settings=settings, sources=[_source("alpha", 3)])

    assert stats["fetched"] == 3
    assert stats["unique"] == 3
    assert stats["new"] == 3
    assert stats["scored"] == 3
    assert stats["total_jobs"] == 3
    assert stats["live_sources"] == 1
    assert stats["failed_sources"] == 0
    assert jobs_repo.count() == 3


def test_every_new_job_gets_a_score(db, settings):
    run_ingest(settings=settings, sources=[_source("alpha", 2)])
    for job_id in [row["id"] for row in jobs_repo.query()[0]]:
        assert scores_repo.get(job_id) is not None


def test_ingest_records_source_runs(db, settings):
    run_ingest(settings=settings, sources=[_source("alpha", 1)])
    latest = sources_repo.latest_per_source()
    assert latest["alpha"]["ok"] == 1
    assert latest["alpha"]["jobs"] == 1
    assert sources_repo.success_rate("alpha") == 1.0


# ---------------------------------------------------------------- انزوای خطا


def test_source_failure_does_not_stop_the_others(db, settings):
    healthy = _source("healthy", 2)
    stats = run_ingest(settings=settings, sources=[
        healthy, FakeSource("broken", error="اتصال قطع شد")])

    assert stats["new"] == 2
    assert stats["live_sources"] == 1
    assert stats["failed_sources"] == 1
    assert jobs_repo.count() == 2


def test_failed_source_is_reported_with_its_own_reason(db, settings):
    stats = run_ingest(settings=settings, sources=[
        FakeSource("broken", error="مهلت تمام شد")])

    broken = next(s for s in stats["sources"] if s["key"] == "broken")
    assert broken["ok"] is False
    assert broken["error"] == "مهلت تمام شد"

    latest = sources_repo.latest_per_source()
    assert latest["broken"]["ok"] == 0
    assert latest["broken"]["error"] == "مهلت تمام شد"


def test_unexpected_exception_is_also_isolated(db, settings):
    """خطای پیش‌بینی‌نشدهٔ یک منبع هم نباید به خط لوله سرایت کند."""
    stats = run_ingest(settings=settings, sources=[
        FakeSource("weird", error=ValueError("چیزی عجیب")), _source("healthy", 1)])

    assert stats["failed_sources"] == 1
    assert stats["new"] == 1


# ---------------------------------------------------------------- صداقت داده


def test_no_source_and_no_seed_leaves_the_list_empty(db, settings):
    stats = run_ingest(settings=settings, allow_seed=False, sources=[
        FakeSource("a", error="down"), FakeSource("b", error="down")])

    assert stats["seeded"] is False
    assert stats["fetched"] == 0
    assert stats["new"] == 0
    assert jobs_repo.count() == 0
    assert stats["message"] == "هیچ آگهی تازه‌ای واکشی نشد"


def test_empty_result_is_explained_not_hidden(db, settings):
    run_ingest(settings=settings, allow_seed=False,
               sources=[FakeSource("a", error="down")])

    kinds = [event["kind"] for event in activity.grouped(limit=20)]
    assert "ingest_empty" in kinds
    assert "source_error" in kinds


def test_seed_used_only_when_explicitly_allowed(db, settings):
    stats = run_ingest(settings=settings, allow_seed=True,
                       sources=[FakeSource("a", error="down")])

    assert stats["seeded"] is True
    assert stats["new"] > 0
    assert any(s["key"] == "seed" for s in stats["sources"])
    assert jobs_repo.count() > 0


def test_seed_is_never_used_when_a_real_source_answers(db, settings):
    """دانهٔ نمونه باید آخرین چاره باشد، نه میان‌بر."""
    stats = run_ingest(settings=settings, allow_seed=True, sources=[_source("alpha", 1)])
    assert stats["seeded"] is False
    assert not any(s["key"] == "seed" for s in stats["sources"])


# ---------------------------------------------------------------- حذف تکراری


def test_same_job_from_two_sources_appears_once(db, settings):
    first = FakeSource("alpha", [raw_job(source="alpha", index=1,
                                         title="Python Developer", company="Acme")])
    second = FakeSource("beta", [raw_job(source="beta", index=9,
                                         title="Python Developer", company="Acme")])

    stats = run_ingest(settings=settings, sources=[first, second])

    assert stats["duplicates_cross_source"] == 1
    assert stats["new"] == 1
    assert stats["total_jobs"] == 1


def test_second_run_does_not_insert_the_same_jobs_again(db, settings):
    sources = [_source("alpha", 3)]
    first = run_ingest(settings=settings, sources=sources)
    second = run_ingest(settings=settings, sources=[_source("alpha", 3)])

    assert first["new"] == 3
    assert second["new"] == 0
    assert second["known"] == 3
    assert second["total_jobs"] == 3


def test_jobs_without_a_title_are_dropped(db, settings):
    blank = FakeSource("alpha", [raw_job(source="alpha", index=1, title="   ")])
    stats = run_ingest(settings=settings, sources=[blank])
    assert stats["unique"] == 0
    assert jobs_repo.count() == 0


# ---------------------------------------------------------------- پیام و پاک‌سازی


def test_summary_message_has_no_latin_digits(db, settings):
    """قاعدهٔ محصول: پیام نمایشی فقط رقم فارسی دارد."""
    stats = run_ingest(settings=settings, sources=[_source("alpha", 4)])
    assert not has_latin_digit(stats["message"]), stats["message"]
    assert fa_number(4) in stats["message"]


def test_ingest_is_logged_as_activity(db, settings):
    stats = run_ingest(settings=settings, sources=[_source("alpha", 2)])
    events = activity.grouped(limit=10)
    done = next(e for e in events if e["kind"] == "ingest_done")
    assert done["meta"]["new"] == stats["new"]
    assert done["level"] == "success"


def test_prune_keeps_the_database_within_the_configured_cap(db, settings):
    tuned = replace(settings, max_jobs=2)
    stats = run_ingest(settings=tuned, sources=[_source("alpha", 5)])

    assert stats["pruned"]["removed_overflow"] > 0
    assert jobs_repo.count() == 2


# ---------------------------------------------------------------- تکمیلی و کمکی


def test_score_pending_backfills_jobs_without_a_score(db, settings):
    job_id, _ = jobs_repo.upsert(normalize(raw_job(index=1)))
    assert scores_repo.get(job_id) is None

    assert score_pending() == 1
    assert scores_repo.get(job_id) is not None


def test_score_pending_is_a_no_op_when_everything_is_scored(db, settings):
    run_ingest(settings=settings, sources=[_source("alpha", 1)])
    assert score_pending() == 0


def test_rescore_job_reflects_the_current_profile(db, settings):
    run_ingest(settings=settings, sources=[_source("alpha", 1)])
    rows, _ = jobs_repo.query()
    job_id = rows[0]["id"]

    assert rescore_job(job_id) == job_id
    assert scores_repo.get(job_id) is not None


def test_rescore_unknown_job_returns_none(db, settings):
    assert rescore_job(999_999) is None


def test_known_sources_lists_the_registry_and_custom_feeds(db, settings):
    keys = [item["key"] for item in known_sources()]
    assert "jobvision" in keys and "remotive" in keys
    assert "custom_feeds" in keys
    assert all(item["label"] for item in known_sources())
