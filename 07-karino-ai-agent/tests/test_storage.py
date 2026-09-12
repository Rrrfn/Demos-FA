# -*- coding: utf-8 -*-
"""آزمون‌های لایهٔ حافظه — درج، فیلتر، صفحه‌بندی، پاک‌سازی و روابط."""

from __future__ import annotations

import time

from karino.pipeline.normalize import normalize
from karino.pipeline.scoring import score
from karino.storage import activity, jobs, proposals, saved, scores, sources

from .fakes import raw_job

NOW = 1_800_000_000


def _store(index: int = 1, **overrides):
    job = normalize(raw_job(index=index, **overrides))
    job_id, is_new = jobs.upsert(job, now=NOW)
    return job, job_id, is_new


# ---------------------------------------------------------------- آگهی‌ها


def test_upsert_inserts_then_updates(db):
    job, job_id, is_new = _store(1)
    assert is_new is True
    assert jobs.count() == 1

    again = normalize(raw_job(index=1))
    same_id, is_new_again = jobs.upsert(again, now=NOW + 600)
    assert same_id == job_id
    assert is_new_again is False
    assert jobs.count() == 1

    row = jobs.get(job_id)
    assert row["seen_count"] == 2                     # «هنوز باز است» یک سیگنال است
    assert row["last_seen_ts"] == NOW + 600


def test_upsert_recovers_when_another_worker_inserted_first(db):
    """دو کارگر می‌توانند هم‌زمان درج کنند؛ دومی نباید خطا بدهد.

    فاصلهٔ میان «بررسی وجود» و «درج» بازهٔ مسابقه است. حتی اگر بررسی بگوید
    رکورد نیست، درج ممکن است قید یکتایی را بشکند — و باید به به‌روزرسانی
    همان رکورد برگردد، نه شکست.
    """
    from karino.storage.jobs import _insert_or_touch

    job = normalize(raw_job(index=1))

    # کارگر اول زودتر درج کرده است (بدون اینکه مسیر upsert را صدا بزند)
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO jobs (source, external_id, fingerprint, title, "
            "first_seen_ts, last_seen_ts, seen_count) VALUES (?,?,?,?,?,?,1)",
            (job.source, job.external_id, job.fingerprint, job.title, NOW, NOW))

    # کارگر دوم همان درج را امتحان می‌کند و قید یکتایی را می‌شکند
    with db.connection() as conn:
        job_id, is_new = _insert_or_touch(conn, job, NOW + 30)

    assert is_new is False
    assert jobs.count() == 1
    assert jobs.get(job_id)["seen_count"] == 2
    assert jobs.get(job_id)["last_seen_ts"] == NOW + 30


def test_upsert_does_not_lose_salary_on_update(db):
    """نسخهٔ بعدی آگهی ممکن است حقوق نداشته باشد؛ مقدار قبلی نباید پاک شود."""
    _, job_id, _ = _store(1, salary_min=5000, salary_max=9000, salary_text="$5,000 – $9,000")
    jobs.upsert(normalize(raw_job(index=1, salary_min=None, salary_max=None, salary_text="")),
                now=NOW + 60)
    row = jobs.get(job_id)
    assert row["salary_min"] == 5000


def test_query_filters_and_paginates(db):
    for index in range(1, 8):
        job, job_id, _ = _store(index, title=f"Python Developer {index}", company="Acme")
        scores.save(job_id, score(job, now=NOW), now=NOW)

    rows, total = jobs.query(per_page=3, page=1, sort="score")
    assert total == 7
    assert len(rows) == 3

    rows_page3, _ = jobs.query(per_page=3, page=3, sort="score")
    assert len(rows_page3) == 1


def test_query_search_matches_title_company_and_description(db):
    # آگهی دوم عمداً برچسب ندارد؛ وگرنه برچسب مشترک پیش‌فرض باعث می‌شود
    # جست‌وجوی «Flask» هر دو را پیدا کند و آزمون، چیزی را بسنجد که نمی‌خواهد.
    _store(1, title="برنامه‌نویس پایتون", company="شرکت آلفا", description="کار با Flask")
    _store(2, title="کارشناس فروش", company="شرکت بتا",
           description="تماس با مشتری", tags=[])

    assert jobs.query(q="پایتون")[1] == 1
    assert jobs.query(q="آلفا")[1] == 1
    assert jobs.query(q="Flask")[1] == 1
    assert jobs.query(q="ناموجود")[1] == 0


def test_query_search_finds_tags_case_insensitively(db):
    """جست‌وجو باید برچسب را هم ببیند، حتی با بزرگی/کوچکی متفاوت."""
    _store(1, title="نقش نامرتبط", company="شرکت", description="متن",
           tags=["flask", "python"])
    assert jobs.query(q="Flask")[1] == 1


def test_query_filters_by_score_and_source(db):
    for index in range(1, 4):
        job, job_id, _ = _store(index, source="alpha")
        scores.save(job_id, score(job, now=NOW), now=NOW)

    assert jobs.query(source="alpha")[1] == 3
    assert jobs.query(source="beta")[1] == 0
    assert jobs.query(min_score=101)[1] == 0


def test_query_sorts_by_score_descending(db):
    low, low_id, _ = _store(1, title="کارشناس فروش", description="تماس با مشتری", tags=[])
    high, high_id, _ = _store(2, title="برنامه‌نویس پایتون و Flask")
    scores.save(low_id, score(low, now=NOW), now=NOW)
    scores.save(high_id, score(high, now=NOW), now=NOW)

    rows, _ = jobs.query(sort="score")
    assert rows[0]["total"] >= rows[-1]["total"]
    assert rows[0]["id"] == high_id


def test_existing_fingerprints_returns_distinct_set(db):
    _store(1)
    _store(2)
    _store(3)
    assert len(jobs.existing_fingerprints()) == 3


def test_prune_removes_stale_but_never_saved(db):
    # خط لولهٔ واقعی یک زمان واحد به یکسان‌سازی و ذخیره می‌دهد. اگر اینجا
    # زمان به یکسان‌سازی پاس نشود، ساعت واقعی مبنا می‌شود و آگهی «تازه»
    # به‌اشتباه کهنه به حساب می‌آید — همان چیزی که این آزمون می‌سنجد.
    fresh = normalize(raw_job(index=1, published_ts=NOW - 3600), now=NOW)
    fresh_id, _ = jobs.upsert(fresh, now=NOW)
    stale, stale_id, _ = _store(2, published_ts=NOW - 400 * 86_400)
    keep, keep_id, _ = _store(3, published_ts=NOW - 400 * 86_400)
    saved.add(keep_id, now=NOW)

    result = jobs.prune(max_jobs=100, max_age_days=45, now=NOW)

    assert result["removed_stale"] == 1
    assert jobs.get(stale_id) is None
    assert jobs.get(fresh_id) is not None
    assert jobs.get(keep_id) is not None       # تصمیم کاربر بر پاک‌سازی مقدم است


def test_prune_respects_max_jobs_cap(db):
    ids = [_store(index, published_ts=NOW - index)[1] for index in range(1, 11)]
    jobs.prune(max_jobs=5, max_age_days=3650, now=NOW)
    assert jobs.count() == 5


def test_count_since_counts_only_new(db):
    _store(1)
    assert jobs.count_since(NOW) == 1
    assert jobs.count_since(NOW + 1) == 0


def test_source_breakdown_groups_by_source(db):
    _store(1, source="alpha")
    _store(2, source="alpha")
    _store(3, source="beta")
    rows = {row["source"]: row["jobs"] for row in jobs.source_breakdown()}
    assert rows == {"alpha": 2, "beta": 1}


# ---------------------------------------------------------------- امتیازها


def test_scores_roundtrip_preserves_breakdown(db):
    job, job_id, _ = _store(1)
    result = score(job, now=NOW)
    scores.save(job_id, result, now=NOW)

    row = scores.get(job_id)
    assert row["total"] == result.total
    assert row["verdict"] == result.verdict
    assert len(__import__("json").loads(row["factors"])) == len(result.factors)


def test_scores_upsert_overwrites(db):
    job, job_id, _ = _store(1)
    scores.save(job_id, score(job, now=NOW), now=NOW)
    scores.save(job_id, score(job, now=NOW), now=NOW + 10)
    assert db.connection() is not None
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 1


def test_unscored_job_ids_lists_pending(db):
    _, scored_id, _ = _store(1)
    _, pending_id, _ = _store(2)
    scores.save(scored_id, score(normalize(raw_job(index=1)), now=NOW), now=NOW)

    assert scores.unscored_job_ids() == [pending_id]


def test_score_distribution_buckets(db):
    for index in range(1, 4):
        job, job_id, _ = _store(index)
        scores.save(job_id, score(job, now=NOW), now=NOW)

    distribution = scores.distribution()
    assert sum(distribution.values()) == 3
    assert set(distribution) == {"0-39", "40-54", "55-71", "72-84", "85-100"}


def test_average_score_of_empty_db_is_zero(db):
    assert scores.average() == 0.0


# ---------------------------------------------------------------- پیشنهادها


def test_proposals_keyed_by_tone_and_variant(db):
    _, job_id, _ = _store(1)
    proposals.save(job_id, "متن رسمی", "rule_based", tone="formal", variant="standard", now=NOW)
    proposals.save(job_id, "متن کوتاه", "rule_based", tone="concise", variant="short", now=NOW)

    assert proposals.get(job_id, tone="formal")["body"] == "متن رسمی"
    assert proposals.get(job_id, tone="concise", variant="short")["body"] == "متن کوتاه"
    assert len(proposals.list_for_job(job_id)) == 2


def test_proposals_same_key_is_replaced_not_duplicated(db):
    _, job_id, _ = _store(1)
    proposals.save(job_id, "نسخهٔ اول", "rule_based", now=NOW)
    proposals.save(job_id, "نسخهٔ دوم", "llm", now=NOW + 5)

    assert proposals.get(job_id)["body"] == "نسخهٔ دوم"
    assert proposals.get(job_id)["writer"] == "llm"
    assert proposals.count() == 1


def test_proposals_deleted_with_job(db):
    """حذف آگهی باید پیشنهادش را هم ببرد، وگرنه رکورد یتیم می‌ماند."""
    _, job_id, _ = _store(1)
    proposals.save(job_id, "متن", "rule_based", now=NOW)
    with db.connection() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    assert proposals.get(job_id) is None


# ---------------------------------------------------------------- ذخیره‌شده


def test_saved_add_remove_and_toggle(db):
    _, job_id, _ = _store(1)
    assert saved.add(job_id, now=NOW) is True
    assert saved.add(job_id, now=NOW) is False      # دوباره‌افزودن بی‌اثر است
    assert saved.is_saved(job_id) is True
    assert saved.count() == 1

    assert saved.toggle(job_id) is False            # برداشته شد
    assert saved.is_saved(job_id) is False
    assert saved.toggle(job_id) is True
    assert saved.remove(job_id) is True
    assert saved.remove(job_id) is False


# ---------------------------------------------------------------- گزارش منابع


def test_source_runs_record_and_latest(db):
    sources.record("alpha", ok=True, jobs=12, duration_ms=90, now=NOW)
    sources.record("alpha", ok=False, error="timeout", now=NOW + 60)
    sources.record("beta", ok=True, jobs=3, now=NOW + 120)

    latest = sources.latest_per_source()
    assert latest["alpha"]["ok"] == 0
    assert latest["alpha"]["error"] == "timeout"
    assert latest["alpha"]["last_success_ts"] == NOW
    assert latest["beta"]["jobs"] == 3


def test_source_success_rate_reflects_history(db):
    for index in range(4):
        sources.record("alpha", ok=(index != 1), now=NOW + index)
    assert sources.success_rate("alpha") == 0.75
    assert sources.success_rate("unknown") == 0.0


def test_source_history_is_capped(db):
    for index in range(70):
        sources.record("alpha", ok=True, jobs=index, now=NOW + index)
    assert len(sources.history("alpha", limit=100)) <= 50


def test_recent_errors_only_lists_failures(db):
    sources.record("alpha", ok=True, now=NOW)
    sources.record("beta", ok=False, error="blocked", now=NOW + 1)

    errors = sources.recent_errors()
    assert [row["source"] for row in errors] == ["beta"]


# ---------------------------------------------------------------- فعالیت


def test_activity_log_and_read(db):
    activity.log("ingest_done", "۲ آگهی تازه", level="success", meta={"new": 2}, now=NOW)
    events = activity.grouped(limit=5)

    assert events[0]["message"] == "۲ آگهی تازه"
    assert events[0]["meta"] == {"new": 2}
    assert activity.count_by_level()["success"] == 1


def test_activity_rejects_unknown_level(db):
    activity.log("x", "پیام", level="nonsense", now=NOW)
    assert activity.grouped()[0]["level"] == "info"


def test_activity_filter_by_level(db):
    activity.log("a", "یک", level="info", now=NOW)
    activity.log("b", "دو", level="error", now=NOW + 1)

    assert len(activity.recent(level="error")) == 1
    assert len(activity.recent()) == 2


def test_activity_is_capped(db):
    for index in range(340):
        activity.log("x", f"رویداد {index}", now=NOW + index)
    assert len(activity.recent(limit=1000)) <= 300
