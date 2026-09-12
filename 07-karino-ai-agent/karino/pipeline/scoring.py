# -*- coding: utf-8 -*-
"""موتور تطبیق — امتیازدهی عاملی و کاملاً توضیح‌پذیر.

طراحی روی یک اصل بنا شده: **عدد بدون مدرک، جعبه‌سیاه است.** بنابراین امتیاز
از نُه عامل ساخته می‌شود که مجموع سقفشان دقیقاً ۱۰۰ است، و هر عامل مدرک
خودش را برمی‌گرداند. صفحهٔ «تحلیل تطابق» همان عوامل را رندر می‌کند و کاربر
می‌بیند ۸۷ از کجا آمده — کدام عامل کامل گرفته و کدام ناقص.

وزن‌ها عامدانه تخصص‌محورند: مهارت ۴۰ نمره دارد و «محل» فقط ۴، چون محل
تعیین‌کنندهٔ اصلی توان انجام کار نیست.
"""
from __future__ import annotations

import time

from ..core.models import Job, ScoreFactor, ScoreResult, VERDICT_LABELS
from ..core.text import (detect_engagement, detect_seniority, fa_number,
                         freshness_band, normalize_fa, search_key)
from ..profile import (PREFS, SKILL_TARGET_WEIGHT, SKILLS, match_skills)

#: سقف هر عامل — مجموع باید ۱۰۰ باشد (تست این را قفل می‌کند)
BUDGETS = {
    "skills": 40.0,
    "core_stack": 10.0,
    "seniority": 10.0,
    "engagement": 10.0,
    "recency": 9.0,
    "remote": 8.0,
    "budget": 6.0,
    "location": 4.0,
    "client_signals": 3.0,
}

FACTOR_LABELS = {
    "skills": "تطبیق مهارت",
    "core_stack": "تخصص اصلی در عنوان",
    "seniority": "سطح ارشدیت",
    "engagement": "نوع همکاری",
    "recency": "تازگی آگهی",
    "remote": "دورکاری",
    "budget": "شفافیت بودجه",
    "location": "محل کار",
    "client_signals": "نشانه‌های کارفرمای جدی",
}

#: سطح ارشدیت آگهی نسبت به سطح هدف → ضریب
SENIORITY_FIT = {
    ("senior", "senior"): 1.00,
    ("senior", "mid"): 0.55,
    ("senior", "junior"): 0.10,
    ("senior", "unknown"): 0.50,
    ("mid", "mid"): 1.00,
    ("mid", "senior"): 0.75,
    ("mid", "junior"): 0.30,
    ("mid", "unknown"): 0.50,
    ("junior", "junior"): 1.00,
    ("junior", "mid"): 0.60,
    ("junior", "senior"): 0.20,
    ("junior", "unknown"): 0.50,
}


def score(job: Job, *, now: int | None = None) -> ScoreResult:
    """امتیاز ۰..۱۰۰ با تحلیل عاملی کامل."""
    now = int(now if now is not None else time.time())
    haystack = search_key(job.text_for_matching)
    title_key = search_key(job.title)

    matched, missing = match_skills(haystack)
    seniority = detect_seniority(haystack)
    engagement = _engagement(job, haystack)

    factors = [
        _skills_factor(matched, missing),
        _core_stack_factor(matched, title_key),
        _seniority_factor(seniority),
        _engagement_factor(engagement),
        _recency_factor(job.published_ts, now),
        _remote_factor(job),
        _budget_factor(job),
        _location_factor(job),
        _client_signals_factor(job),
    ]

    total = int(round(sum(f.points for f in factors)))
    total = max(0, min(100, total))

    return ScoreResult(
        total=total,
        verdict=verdict_for(total),
        matched_skills=matched,
        missing_skills=missing,
        factors=factors,
        reasons=reasons_from(factors, matched, missing),
        seniority=seniority,
        engagement=engagement,
        remote=job.remote,
    )


# ---------------------------------------------------------------- عامل‌ها


def _skills_factor(matched: list[str], missing: list[str]) -> ScoreFactor:
    """سهم وزنی مهارت‌های منطبق از یک هدف واقع‌بینانه."""
    budget = BUDGETS["skills"]
    weight = sum(SKILLS[k].weight for k in matched if k in SKILLS)
    ratio = min(1.0, weight / SKILL_TARGET_WEIGHT) if weight else 0.0
    points = round(budget * ratio, 1)

    top = sorted(matched, key=lambda k: -SKILLS[k].weight)[:6]
    evidence = [f"{SKILLS[k].fa} (وزن {fa_number(SKILLS[k].weight)})" for k in top]

    if matched:
        detail = (f"{fa_number(len(matched))} مهارت منطبق با وزن کل "
                  f"{fa_number(weight)} از هدف {fa_number(SKILL_TARGET_WEIGHT)}")
    else:
        detail = "هیچ مهارت شناخته‌شده‌ای در آگهی پیدا نشد"

    return ScoreFactor("skills", FACTOR_LABELS["skills"], points, budget, detail, evidence)


def _core_stack_factor(matched: list[str], title_key: str) -> ScoreFactor:
    """حضور تخصص اصلی (وزن ۸ به بالا) در عنوان آگهی — سیگنال تمرکز واقعی پروژه."""
    budget = BUDGETS["core_stack"]
    hits: list[str] = []
    for key in matched:
        spec = SKILLS.get(key)
        if not spec or spec.weight < 8:
            continue
        if any(_in_title(title_key, p) for p in spec.patterns):
            hits.append(spec.fa)

    if not hits:
        return ScoreFactor("core_stack", FACTOR_LABELS["core_stack"], 0.0, budget,
                           "تخصص اصلی پروفایل در عنوان آگهی دیده نشد")

    points = budget if len(hits) >= 2 else round(budget * 0.65, 1)
    detail = f"{fa_number(len(hits))} تخصص اصلی در عنوان"
    return ScoreFactor("core_stack", FACTOR_LABELS["core_stack"], points, budget,
                       detail, hits[:4])


def _in_title(title_key: str, pattern: str) -> bool:
    p = pattern.lower().strip()
    return bool(p) and p in title_key


def _seniority_factor(seniority: str) -> ScoreFactor:
    budget = BUDGETS["seniority"]
    target = PREFS.target_seniority
    fit = SENIORITY_FIT.get((target, seniority), 0.5)
    points = round(budget * fit, 1)
    detail = (f"سطح آگهی «{_fa_level(seniority)}» در برابر سطح هدف "
              f"«{_fa_level(target)}»")
    return ScoreFactor("seniority", FACTOR_LABELS["seniority"], points, budget, detail)


def _fa_level(level: str) -> str:
    from ..core.models import SENIORITY_LABELS

    return SENIORITY_LABELS.get(level, level)


def _engagement(job: Job, haystack: str) -> str:
    """نوع همکاری — همان چیزی که لایهٔ یکسان‌سازی تعیین کرده است.

    اگر لایهٔ یکسان‌سازی مقدار را به کلیدهای استاندارد نگاشته باشد، اینجا
    دوباره از متن استنتاج نمی‌کنیم؛ دو منبع حقیقت یعنی امکان ناهم‌خوانی
    بین برچسبی که کاربر می‌بیند و امتیازی که می‌گیرد.
    """
    from ..core.models import ENGAGEMENT_LABELS

    explicit = (job.employment or "").lower().strip()
    if explicit in ENGAGEMENT_LABELS:
        return explicit
    if "full" in explicit:
        return "fulltime"
    if any(w in explicit for w in ("contract", "freelance", "part")):
        return "freelance"
    if "intern" in explicit:
        return "internship"
    return detect_engagement(haystack)


def _engagement_factor(engagement: str) -> ScoreFactor:
    budget = BUDGETS["engagement"]
    from ..core.models import ENGAGEMENT_LABELS

    if engagement in PREFS.preferred_engagement:
        ratio, note = 1.0, "هم‌راستا با نوع همکاری ترجیحی"
    elif engagement in PREFS.disliked_engagement:
        ratio, note = 0.0, "خارج از محدودهٔ نوع همکاری مطلوب"
    elif engagement == "unknown":
        ratio, note = 0.45, "نوع همکاری در آگهی مشخص نشده"
    else:
        ratio, note = 0.35, "نوع همکاری نامطلوب اما قابل بررسی"

    detail = f"{ENGAGEMENT_LABELS.get(engagement, engagement)} — {note}"
    return ScoreFactor("engagement", FACTOR_LABELS["engagement"],
                       round(budget * ratio, 1), budget, detail)


def _recency_factor(published_ts: int | None, now: int) -> ScoreFactor:
    budget = BUDGETS["recency"]
    band = freshness_band(published_ts, now=now)
    ratio = {"fresh": 1.0, "recent": 0.66, "aging": 0.33, "stale": 0.0}.get(band, 0.0)

    from ..core.text import relative_time

    if band == "unknown":
        detail = "تاریخ انتشار در دسترس نیست"
        ratio = 0.0
    else:
        detail = f"منتشرشده {relative_time(published_ts, now=now)}"
    return ScoreFactor("recency", FACTOR_LABELS["recency"],
                       round(budget * ratio, 1), budget, detail)


def _remote_factor(job: Job) -> ScoreFactor:
    """دورکاری فقط از فیلد یکسان‌شدهٔ آگهی خوانده می‌شود.

    لایهٔ یکسان‌سازی قبلاً پرچم صریح منبع، محل و متن را با هم دیده و
    ``job.remote`` را ساخته است. اگر اینجا دوباره از متن استنتاج کنیم،
    دو منبع حقیقت پیدا می‌کنیم و ممکن است امتیاز با همان چیزی که در کارت
    آگهی نمایش داده می‌شود ناهمخوان شود.
    """
    budget = BUDGETS["remote"]
    remote = bool(job.remote)
    if remote and PREFS.prefers_remote:
        points, detail = budget, "دورکاری و منطبق با ترجیح"
    elif remote:
        points, detail = round(budget * 0.5, 1), "دورکاری، بدون ترجیح خاص"
    else:
        points, detail = round(budget * 0.25, 1), "حضوری یا نامشخص"
    return ScoreFactor("remote", FACTOR_LABELS["remote"], points, budget, detail)


def _budget_factor(job: Job) -> ScoreFactor:
    budget = BUDGETS["budget"]
    if job.salary_min and job.salary_max:
        points = budget
        detail = f"بازهٔ بودجه اعلام شده ({job.salary_text or 'مشخص'})"
    elif job.salary_min or job.salary_max or job.salary_text:
        points = round(budget * 0.5, 1)
        detail = f"بودجه به‌صورت متنی آمده ({job.salary_text or 'مشخص'})"
    else:
        points = 0.0
        detail = "کارفرما بودجه را اعلام نکرده"
    return ScoreFactor("budget", FACTOR_LABELS["budget"], points, budget, detail)


def _location_factor(job: Job) -> ScoreFactor:
    budget = BUDGETS["location"]
    location = search_key(job.location)
    if job.remote:
        return ScoreFactor("location", FACTOR_LABELS["location"], budget, budget,
                           "محل محدود نمی‌کند (دورکاری)")
    if not location or location in ("-", "nan"):
        return ScoreFactor("location", FACTOR_LABELS["location"],
                           round(budget * 0.5, 1), budget,
                           "محل کار اعلام نشده")
    if any(pref in location for pref in PREFS.preferred_locations):
        return ScoreFactor("location", FACTOR_LABELS["location"], budget, budget,
                           f"محل «{job.location}» در محدودهٔ مطلوب")
    return ScoreFactor("location", FACTOR_LABELS["location"],
                       round(budget * 0.25, 1), budget,
                       f"محل «{job.location}» بیرون از محدودهٔ مطلوب")


def _client_signals_factor(job: Job) -> ScoreFactor:
    """نشانه‌های «درخواست واقعی و جدی»، نه آگهی مبهم یا اسپم.

    فهرست بررسی‌ها یک‌جا تعریف می‌شود تا مخرج کسر و شمارندهٔ شواهد از یک
    منبع بیایند؛ وگرنه ممکن است متن «۵ نشانه از ۴ نشانه» چاپ کند.
    """
    budget = BUDGETS["client_signals"]
    haystack = search_key(job.text_for_matching)
    checks = (
        (bool(job.company.strip()), "نام کارفرما مشخص است"),
        (len(job.description) >= 400, "شرح پروژه مفصل است"),
        (any(w in haystack for w in PREFS.client_signal_words),
         "نشانهٔ استخدام/همکاری در متن"),
        (len(job.tags) >= 3, "برچسب‌های فنی متنوع"),
        (bool(job.url), "لینک مرجع برای بررسی"),
    )
    signals = [label for present, label in checks if present]

    points = round(budget * min(1.0, len(signals) / len(checks)), 1)
    detail = (f"{fa_number(len(signals))} نشانه از {fa_number(len(checks))} نشانهٔ کارفرمای جدی"
              if signals else "نشانهٔ خاصی از کارفرمای جدی دیده نشد")
    return ScoreFactor("client_signals", FACTOR_LABELS["client_signals"],
                       points, budget, detail, signals)


# ---------------------------------------------------------------- کمکی‌ها


def verdict_for(total: int) -> str:
    if total >= 85:
        return "excellent"
    if total >= 72:
        return "strong"
    if total >= 55:
        return "moderate"
    return "weak"


def verdict_label(verdict: str) -> str:
    return VERDICT_LABELS.get(verdict, verdict)


def reasons_from(factors: list[ScoreFactor], matched: list[str],
                 missing: list[str]) -> list[str]:
    """دلایل فارسی مرتب‌شده بر اساس اثر واقعی هر عامل بر امتیاز.

    مرتب‌سازی بر پایهٔ سهم ازدست‌رفته است، نه ترتیب ثابت: کاربر باید اول
    ببیند کدام عامل کم آورده.
    """
    ordered = sorted(factors, key=lambda f: -(f.max_points - f.points))
    reasons: list[str] = []

    for factor in ordered:
        if factor.points >= factor.max_points:
            reasons.append(f"✔ {factor.label} کامل — {factor.detail}")
        elif factor.points > 0:
            reasons.append(f"◐ {factor.label} نسبی — {factor.detail}")
        else:
            reasons.append(f"✘ {factor.label} بی‌اثر — {factor.detail}")

    if matched:
        from ..profile import fa_names

        names = "، ".join(fa_names(sorted(matched, key=lambda k: -SKILLS[k].weight), 5))
        reasons.insert(0, f"مهارت‌های منطبق: {names}")
    if missing:
        from ..profile import fa_names

        gaps = fa_names([k for k in missing if SKILLS[k].weight >= 8], 4)
        if gaps:
            reasons.append("شکاف‌های مهم در آگهی: " + "، ".join(gaps))

    return reasons
