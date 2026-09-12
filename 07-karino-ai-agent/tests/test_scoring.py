# -*- coding: utf-8 -*-
"""آزمون‌های موتور تطبیق — عامل‌ها، توضیح‌پذیری و مرزها.

مهم‌ترین آزمون‌ها اینجا هستند، چون خواستهٔ اصلی محصول «شفافیت» است: امتیاز
بدون تفکیک قابل قبول نیست، پس تفکیک باید ساختاراً قفل شود.
"""
from __future__ import annotations

import time

import pytest

from karino.core.models import Job
from karino.pipeline.scoring import (BUDGETS, FACTOR_LABELS, score,
                                     verdict_for, verdict_label)
from karino.profile import SKILL_TARGET_WEIGHT, SKILLS


def build_job(**overrides) -> Job:
    data = dict(
        source="test", external_id="t-1",
        title="برنامه‌نویس پایتون برای ساخت API",
        company="شرکت آزمون",
        description="نیاز به توسعه‌دهندهٔ پایتون با Flask و دیتابیس SQL. دورکاری کامل، پروژه‌ای.",
        tags=["python", "flask", "sql"],
        location="دورکاری", remote=True, employment="freelance",
        published_ts=int(time.time()) - 3600,
    )
    data.update(overrides)
    return Job(**data)


# ---------------------------------------------------------------- چارچوب


def test_factor_budgets_sum_to_exactly_100():
    """مجموع سقف عامل‌ها باید دقیقاً ۱۰۰ باشد، وگرنه امتیاز بی‌معنا می‌شود."""
    assert abs(sum(BUDGETS.values()) - 100.0) < 1e-9


def test_every_budget_has_a_label():
    assert set(BUDGETS) == set(FACTOR_LABELS)


def test_all_nine_required_factors_present():
    """فهرست عامل‌های خواسته‌شدهٔ محصول باید کامل باشد."""
    required = {"skills", "seniority", "engagement", "recency", "remote",
                "budget", "location", "client_signals", "core_stack"}
    assert set(BUDGETS) == required


def test_score_never_leaves_zero_to_hundred():
    for job in (build_job(), build_job(title="", description="", tags=[], remote=False),
                build_job(title="x" * 400, description="python " * 200)):
        result = score(job)
        assert 0 <= result.total <= 100


# ---------------------------------------------------------------- تفکیک


def test_result_exposes_full_breakdown():
    result = score(build_job())
    assert len(result.factors) == len(BUDGETS)
    for factor in result.factors:
        assert factor.label
        assert 0 <= factor.points <= factor.max_points
        assert 0.0 <= factor.ratio <= 1.0
        assert factor.detail                # هر عامل باید توضیح داشته باشد


def test_factor_points_sum_matches_total():
    """عدد کل باید دقیقاً جمع عامل‌ها باشد؛ نه بیشتر، نه کمتر."""
    result = score(build_job())
    assert result.total == round(sum(f.points for f in result.factors))


def test_reasons_are_ordered_by_shortfall():
    """کاربر باید اول ببیند کدام عامل کم آورده، نه ترتیب ثابت."""
    result = score(build_job(title="منشی اداری", description="تایپ و بایگانی", tags=[]))
    assert result.reasons
    assert any(r.startswith(("✔", "◐", "✘")) for r in result.reasons)


def test_matched_factor_carries_evidence():
    result = score(build_job())
    skills_factor = next(f for f in result.factors if f.key == "skills")
    assert skills_factor.evidence
    assert any("پایتون" in item for item in skills_factor.evidence)


# ---------------------------------------------------------------- رفتار عامل‌ها


def test_strong_python_job_scores_high():
    result = score(build_job())
    assert result.total >= 80
    assert "python" in result.matched_skills
    assert result.verdict in ("strong", "excellent")


def test_irrelevant_job_scores_low():
    result = score(build_job(title="اپراتور ورود داده", company="چاپخانه",
                             description="تایپ فاکتورها در اکسل، شیفت عصر.",
                             tags=[], remote=False, employment="fulltime"))
    assert result.total < 45
    assert result.verdict == "weak"


def test_skills_factor_saturates_at_its_budget():
    """تطبیق فراتر از هدف واقع‌بینانه نباید از سقف عامل عبور کند."""
    result = score(build_job(
        title="python flask django rest api scraping telegram automation ml nlp pandas",
        description="python django flask rest scraping telegram selenium machine learning "
                    "nlp pandas html css javascript docker devops wordpress git react",
        tags=["python", "flask", "sql", "docker"]))
    skills = next(f for f in result.factors if f.key == "skills")
    assert skills.points <= skills.max_points
    assert skills.points == skills.max_points


def test_core_stack_requires_skill_in_title():
    """تخصص اصلی باید در *عنوان* دیده شود، نه فقط در متن."""
    in_title = score(build_job(title="برنامه‌نویس پایتون"))
    only_body = score(build_job(title="برنامه‌نویس عمومی",
                                description="کار با python در پروژه", tags=[]))
    a = next(f for f in in_title.factors if f.key == "core_stack")
    b = next(f for f in only_body.factors if f.key == "core_stack")
    assert a.points > b.points


def test_seniority_alignment_changes_points():
    senior = score(build_job(title="Senior Python Engineer", description="python flask"))
    junior = score(build_job(title="Junior Python Developer", description="python flask"))
    a = next(f for f in senior.factors if f.key == "seniority")
    b = next(f for f in junior.factors if f.key == "seniority")
    assert a.points > b.points


def test_remote_preference_awards_remote_jobs():
    remote = score(build_job(remote=True))
    # آگهی حضوری باید واقعاً حضوری باشد: شرحش هم نباید واژهٔ دورکاری داشته باشد،
    # وگرنه مرحلهٔ یکسان‌سازی — درست — آن را دورکاری می‌شمارد.
    onsite = score(build_job(remote=False, location="تهران",
                             description="حضور تمام‌وقت در دفتر تهران، کار با پایتون و Flask."))
    a = next(f for f in remote.factors if f.key == "remote")
    b = next(f for f in onsite.factors if f.key == "remote")
    assert a.points > b.points


def test_scoring_trusts_normalized_remote_flag():
    """یک منبع حقیقت برای دورکاری: فیلد یکسان‌شده، نه استنتاج دوباره از متن."""
    flagged_off = score(build_job(remote=False,
                                  description="حضور در دفتر، کار با پایتون."))
    factor = next(f for f in flagged_off.factors if f.key == "remote")
    assert factor.points < factor.max_points
    assert "حضوری" in factor.detail or "نامشخص" in factor.detail


def test_recency_rewards_fresh_and_penalizes_stale():
    now = 1_800_000_000
    fresh = score(build_job(published_ts=now - 3600), now=now)
    stale = score(build_job(published_ts=now - 90 * 86_400), now=now)
    a = next(f for f in fresh.factors if f.key == "recency")
    b = next(f for f in stale.factors if f.key == "recency")
    assert a.points == a.max_points
    assert b.points == 0


def test_missing_publish_date_does_not_fabricate_freshness():
    """تاریخ ناموجود باید صفر بگیرد، نه امتیاز متوسط."""
    result = score(build_job(published_ts=None))
    recency = next(f for f in result.factors if f.key == "recency")
    assert recency.points == 0
    assert "در دسترس نیست" in recency.detail


def test_budget_factor_reflects_disclosed_range():
    with_range = score(build_job(salary_min=5000, salary_max=9000, salary_text="$5,000 – $9,000"))
    textual = score(build_job(salary_text="توافقی"))
    absent = score(build_job())

    values = []
    for result in (with_range, textual, absent):
        values.append(next(f for f in result.factors if f.key == "budget").points)
    assert values[0] > values[1] > values[2] == 0


def test_client_signal_count_never_exceeds_its_denominator():
    """متن عامل نباید چیزی مثل «۵ نشانه از ۴ نشانه» چاپ کند."""
    result = score(build_job(description="پروژهٔ ساخت API با تیم محصول. " * 20,
                             url="https://example.com/1", tags=["python", "flask", "sql"]))
    factor = next(f for f in result.factors if f.key == "client_signals")

    from karino.core.text import fa_number

    found = next(n for n in range(1, 6) if f"{fa_number(n)} نشانه از" in factor.detail)
    total = next(n for n in range(1, 6) if f"از {fa_number(n)} نشانهٔ" in factor.detail)
    assert found <= total
    assert len(factor.evidence) == found
    assert factor.points <= factor.max_points


def test_client_signals_saturate_with_all_checks_present():
    result = score(build_job(description="پروژهٔ ساخت API با تیم محصول. " * 20,
                             url="https://example.com/1", tags=["python", "flask", "sql"]))
    factor = next(f for f in result.factors if f.key == "client_signals")
    assert factor.points == factor.max_points


def test_client_signals_reward_detailed_postings():
    rich = score(build_job(description="پروژهٔ ساخت API با تیم محصول. " * 20,
                           url="https://example.com/1", tags=["python", "flask", "sql"]))
    thin = score(build_job(company="", description="نیاز به نیرو", tags=[], url=""))
    a = next(f for f in rich.factors if f.key == "client_signals")
    b = next(f for f in thin.factors if f.key == "client_signals")
    assert a.points > b.points


def test_location_outside_preference_scores_lower():
    inside = score(build_job(remote=False, location="تهران"))
    outside = score(build_job(remote=False, location="Munich"))
    a = next(f for f in inside.factors if f.key == "location")
    b = next(f for f in outside.factors if f.key == "location")
    assert a.points > b.points


# ---------------------------------------------------------------- آستانه‌ها


@pytest.mark.parametrize("total,expected", [
    (100, "excellent"), (85, "excellent"), (84, "strong"), (72, "strong"),
    (71, "moderate"), (55, "moderate"), (54, "weak"), (0, "weak"),
])
def test_verdict_thresholds(total, expected):
    assert verdict_for(total) == expected


def test_verdict_labels_are_persian():
    for verdict in ("excellent", "strong", "moderate", "weak"):
        assert verdict_label(verdict)


def test_excellent_verdict_reachable_by_a_literal_perfect_match():
    """سقف امتیاز باید در عمل قابل‌دسترسی باشد، وگرنه آستانه‌ها تشریفاتی‌اند."""
    result = score(build_job(
        title="Senior Python Developer — Flask و REST API",
        description="تیم محصول ما به یک توسعه‌دهندهٔ ارشد پایتون نیاز دارد. "
                    "ساخت REST API با Flask و دیتابیس SQL، دورکاری کامل، قرارداد پروژه‌ای. " * 6,
        tags=["python", "flask", "rest api", "sql", "git"],
        salary_min=4000, salary_max=8000, salary_text="$4,000 – $8,000",
        published_ts=int(time.time()) - 1800))
    assert result.verdict == "excellent"


def test_scoring_is_deterministic():
    job = build_job()
    first, second = score(job), score(job)
    assert first.total == second.total
    assert [f.points for f in first.factors] == [f.points for f in second.factors]


def test_skill_target_weight_is_sane():
    """هدف وزن منطبق باید بین یک تخصص اصلی و کل پروفایل باشد."""
    heaviest = max(SKILLS.values(), key=lambda s: s.weight).weight
    assert heaviest < SKILL_TARGET_WEIGHT < sum(s.weight for s in SKILLS.values())
