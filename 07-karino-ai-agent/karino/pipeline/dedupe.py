# -*- coding: utf-8 -*-
"""حذف تکراری — دو سطح، چون دو نوع تکرار داریم.

۱) تکرار **بین‌منبعی**: یک آگهی هم‌زمان در Remotive و RemoteOK منتشر شده.
   انگشت‌نگاشت (عنوان + شرکت) این‌ها را یکی می‌کند.

۲) تکرار **تقریبی**: عنوان‌ها کمی تفاوت دارند («Senior Python Developer» و
   «Senior Python Developer (Remote)»). شباهت توکنی این‌ها را می‌گیرد.

برندهٔ گروه، «کامل‌ترین» رکورد است نه اولین رکورد — وگرنه ممکن است نسخه‌ای
بدون حقوق و بدون تاریخ برنده شود و دادهٔ ارزشمند از دست برود.
"""
from __future__ import annotations

from ..core.models import Job
from .normalize import similarity

#: آستانهٔ شباهت عنوان برای «همان آگهی» — بالاتر از این یعنی تکرار
SIMILARITY_THRESHOLD = 0.86


def dedupe(jobs: list[Job], *, existing_fingerprints: set[str] | None = None
           ) -> tuple[list[Job], dict]:
    """برگشت: (آگهی‌های یکتا، آمار).

    ورودی می‌تواند خودش تکرار داشته باشد؛ خروجی قطعاً یکتاست.
    """
    existing = set(existing_fingerprints or ())
    stats = {
        "input": len(jobs),
        "duplicate_fingerprint": 0,
        "duplicate_similar": 0,
        "already_known": 0,
        "unique": 0,
    }

    by_fingerprint: dict[str, Job] = {}
    order: list[str] = []

    for job in jobs:
        if not job.title:
            continue

        # ۱) از قبل در پایگاه داده هست
        if job.fingerprint in existing:
            stats["already_known"] += 1
            continue

        # ۲) تکرار دقیق بین‌منبعی
        current = by_fingerprint.get(job.fingerprint)
        if current is not None:
            by_fingerprint[job.fingerprint] = _better(current, job)
            stats["duplicate_fingerprint"] += 1
            continue

        # ۳) تکرار تقریبی — جست‌وجو میان همان شرکت‌ها کافی است و ارزان می‌ماند
        twin_key = _find_similar(job, by_fingerprint)
        if twin_key is not None:
            by_fingerprint[twin_key] = _better(by_fingerprint[twin_key], job)
            stats["duplicate_similar"] += 1
            continue

        by_fingerprint[job.fingerprint] = job
        order.append(job.fingerprint)

    unique = [by_fingerprint[key] for key in order]
    stats["unique"] = len(unique)
    return unique, stats


def _find_similar(job: Job, by_fingerprint: dict[str, Job]) -> str | None:
    """کلید رکورد مشابه، یا None. فقط میان رکوردهای همان شرکت می‌گردد."""
    company = job.company.strip().lower()
    if not company:
        return None
    for key, candidate in by_fingerprint.items():
        if candidate.company.strip().lower() != company:
            continue
        if similarity(job.title, candidate.title) >= SIMILARITY_THRESHOLD:
            return key
    return None


def _quality(job: Job) -> tuple:
    """معیار «کامل‌تر بودن» — مقایسهٔ چند فیلد، نه فقط یکی."""
    return (
        1 if job.salary_min or job.salary_max else 0,   # دادهٔ بودجهٔ عددی
        1 if job.published_ts else 0,                   # تاریخ انتشار
        1 if job.company else 0,                        # نام کارفرما
        min(len(job.description), 2000),                # پرمایگی توضیح
        len(job.tags),
    )


def _better(a: Job, b: Job) -> Job:
    """رکورد کامل‌تر را برمی‌گرداند و فیلدهای ناقص را از دیگری پر می‌کند.

    فقط «انتخاب برنده» کافی نیست: نسخهٔ ضعیف‌تر ممکن است حقوق داشته باشد در
    حالی که برنده ندارد. بنابراین کمبودها از رکورد بازنده پر می‌شوند.
    """
    winner, loser = (a, b) if _quality(a) >= _quality(b) else (b, a)

    if not winner.salary_min and loser.salary_min:
        winner.salary_min = loser.salary_min
        winner.salary_max = loser.salary_max
        winner.salary_text = winner.salary_text or loser.salary_text
    if not winner.published_ts and loser.published_ts:
        winner.published_ts = loser.published_ts
    if not winner.company and loser.company:
        winner.company = loser.company
    if len(loser.description) > len(winner.description):
        winner.description = loser.description
    if not winner.url and loser.url:
        winner.url = loser.url

    # منابع هر دو ثبت می‌شوند تا داشبورد بتواند «چند منبع» را نشان دهد
    winner.tags = list(dict.fromkeys(winner.tags + loser.tags))[:12]
    return winner


def known_fingerprints(rows) -> set[str]:
    """انگشت‌نگاشت رکوردهای پایگاه داده برای پرش سریع."""
    return {row["fingerprint"] for row in rows if row["fingerprint"]}
