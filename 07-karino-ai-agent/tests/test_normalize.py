# -*- coding: utf-8 -*-
"""آزمون‌های یکسان‌سازی و حذف تکراری.

دشوارترین بخش محصول همین است: منابع ناهمگون‌اند و یک آگهی می‌تواند هم‌زمان
در چند جا باشد. اگر این لایه درست کار نکند، داشبورد پر از تکرار می‌شود.
"""
from __future__ import annotations

import time

from karino.pipeline.dedupe import dedupe
from karino.pipeline.normalize import fingerprint, normalize, similarity

from .fakes import raw_job


# ---------------------------------------------------------------- یکسان‌سازی


def test_normalize_strips_html_and_trims_description():
    job = normalize(raw_job(description="<p>" + ("متن " * 900) + "</p>"))
    assert "<p>" not in job.description
    assert len(job.description) <= 2400


def test_normalize_detects_remote_from_location():
    assert normalize(raw_job(remote=None, location="Worldwide")).remote is True
    assert normalize(raw_job(remote=None, location="دورکاری")).remote is True
    assert normalize(raw_job(remote=None, location="تهران",
                             description="حضور در دفتر")).remote is False


def test_normalize_detects_remote_from_description():
    assert normalize(raw_job(remote=None, location="",
                             description="این پروژه دورکاری است.")).remote is True


def test_normalize_trusts_explicit_source_flag():
    """پرچم صریح منبع بر استنتاج متنی مقدم است."""
    assert normalize(raw_job(remote=True, location="تهران",
                             description="حضور در دفتر")).remote is True


def test_normalize_clamps_future_timestamps():
    """تاریخ آینده یعنی منطقهٔ زمانی اشتباه — نه آگهی فردا."""
    future = int(time.time()) + 30 * 86_400
    job = normalize(raw_job(published_ts=future))
    assert job.published_ts <= int(time.time())


def test_normalize_clamp_uses_the_injected_clock():
    """خط لوله یک «اکنون» واحد می‌دهد؛ سقف‌گذاری نباید ساعت دیوار را بخواند.

    اگر اینجا ساعت واقعی مبنا شود، همان آگهی‌ای که خط لوله تازه می‌داند
    با معیار دیگری کهنه می‌شود و دو منبع حقیقت پیدا می‌کنیم.
    """
    now = 1_800_000_000
    future = now + 10 * 86_400
    job = normalize(raw_job(published_ts=future), now=now)
    assert job.published_ts == now

    recent = normalize(raw_job(published_ts=now - 3600), now=now)
    assert recent.published_ts == now - 3600      # بی‌دلیل سقف‌گذاری نمی‌شود


def test_normalize_deduplicates_tags_and_cleans_them():
    """برچسب‌ها بدون حساسیت به بزرگی/کوچکی حروف یکتا می‌شوند و فاصله‌های اضافی می‌ریزند."""
    job = normalize(raw_job(tags=["python", "Python", "  flask  ", ""]))
    assert job.tags == ["python", "flask"]


def test_normalize_canonicalizes_employment_from_source():
    """مقدار منبع محترم است، ولی به کلید استاندارد نگاشته می‌شود.

    بدون این نگاشت، ``full_time`` تا رابط می‌رود و برچسب فارسی پیدا نمی‌کند.
    """
    for raw in ("full_time", "Full-Time", "permanent"):
        assert normalize(raw_job(employment=raw)).employment == "fulltime", raw
    assert normalize(raw_job(employment="Contract")).employment == "freelance"
    assert normalize(raw_job(employment="internship")).employment == "internship"


def test_normalize_detects_engagement_when_source_is_silent():
    assert normalize(raw_job(employment="",
                             description="قرارداد پروژه‌ای برای ساخت API")).employment == "freelance"
    assert normalize(raw_job(employment="",
                             description="نیاز به نیروی متخصص")).employment == "unknown"


def test_fingerprint_is_source_independent():
    """کلید یکتایی نباید به منبع وابسته باشد، وگرنه حذف بین‌منبعی کار نمی‌کند."""
    a = fingerprint("Python Developer", "Acme")
    b = fingerprint("python developer", "ACME")
    assert a == b
    assert fingerprint("Python Developer", "Other") != a


def test_similarity_is_symmetric_and_bounded():
    a = "Senior Python Developer"
    b = "Senior Python Developer (Remote)"
    assert 0 <= similarity(a, b) <= 1
    assert similarity(a, b) == similarity(b, a)
    assert similarity(a, a) == 1.0
    assert similarity("", "x") == 0.0


# ---------------------------------------------------------------- حذف تکراری


def test_dedupe_removes_identical_fingerprint():
    """همان عنوان و همان شرکت از دو منبع مختلف = یک آگهی."""
    jobs = [normalize(raw_job(source="alpha", index=1, title="Python Developer",
                              company="Acme")),
            normalize(raw_job(source="beta", index=2, title="Python Developer",
                              company="Acme"))]
    unique, stats = dedupe(jobs)

    assert len(unique) == 1
    assert stats["duplicate_fingerprint"] == 1


def test_dedupe_keeps_genuinely_different_jobs():
    jobs = [normalize(raw_job(index=1, title="Python Developer", company="Acme")),
            normalize(raw_job(index=2, title="Data Engineer", company="Beta"))]
    unique, _ = dedupe(jobs)
    assert len(unique) == 2


def test_dedupe_skips_jobs_already_in_database():
    job = normalize(raw_job())
    unique, stats = dedupe([job], existing_fingerprints={job.fingerprint})

    assert unique == []
    assert stats["already_known"] == 1


def test_dedupe_prefers_the_richer_record():
    """برنده باید نسخهٔ کامل‌تر باشد، نه آن که اول رسیده."""
    thin = normalize(raw_job(source="alpha", index=1, title="Python Developer",
                             company="Acme", description="", salary_min=None,
                             salary_max=None, salary_text=""))
    rich = normalize(raw_job(source="beta", index=2, title="Python Developer",
                             company="Acme", description="توضیح مفصل " * 40,
                             salary_min=5000, salary_max=9000, salary_text="$5,000 – $9,000"))
    unique, _ = dedupe([thin, rich])

    assert len(unique) == 1
    assert unique[0].salary_min == 5000
    assert len(unique[0].description) > 100


def test_dedupe_merges_fields_from_the_loser():
    """رکورد بازنده نباید داده‌اش گم شود؛ کمبودهای برنده از آن پر می‌شود."""
    no_salary = normalize(raw_job(source="alpha", index=1, title="Python Developer",
                                  company="Acme", salary_min=None, salary_max=None,
                                  salary_text=""))
    with_salary = normalize(raw_job(source="beta", index=2, title="Python Developer",
                                    company="Acme", salary_min=3000, salary_max=6000,
                                    salary_text="$3,000 – $6,000"))
    unique, _ = dedupe([no_salary, with_salary])

    assert unique[0].salary_min == 3000
    assert unique[0].salary_text


def test_dedupe_catches_near_duplicate_titles_same_company():
    a = normalize(raw_job(index=1, title="Senior Python Developer", company="Acme"))
    b = normalize(raw_job(index=2, title="Senior Python Developer (Remote)", company="Acme"))
    unique, stats = dedupe([a, b])

    assert len(unique) == 1
    assert stats["duplicate_similar"] == 1


def test_dedupe_does_not_merge_similar_titles_across_companies():
    """هم‌نامی عنوان در دو شرکت، تکرار نیست."""
    a = normalize(raw_job(index=1, title="Python Developer", company="Acme"))
    b = normalize(raw_job(index=2, title="Python Developer", company="Beta"))
    unique, _ = dedupe([a, b])
    assert len(unique) == 2


def test_dedupe_drops_jobs_without_title():
    """آگهی بی‌عنوان قابل نمایش نیست و باید حذف شود."""
    unique, _ = dedupe([normalize(raw_job(title="")), normalize(raw_job(index=2))])
    assert len(unique) == 1


def test_dedupe_stats_are_consistent():
    jobs = [normalize(raw_job(source="alpha", index=1, title="Python Developer",
                              company="Acme")),
            normalize(raw_job(source="beta", index=2, title="Python Developer",
                              company="Acme")),          # تکراری
            normalize(raw_job(source="alpha", index=3, title="Data Engineer",
                              company="Beta"))]
    unique, stats = dedupe(jobs)
    assert stats["input"] == 3
    assert stats["unique"] == len(unique) == 2
    assert stats["duplicate_fingerprint"] + stats["duplicate_similar"] == 1
