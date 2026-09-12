# -*- coding: utf-8 -*-
"""یکسان‌سازی — تبدیل آگهی خام هر منبع به یک شکل واحد.

منابع، دادهٔ ناهمگون می‌دهند: یکی «دورکاری» را در محل می‌نویسد، دیگری در
توضیح، و آن یکی پرچم بولین دارد. این لایه آن تفاوت‌ها را می‌پوشاند تا
موتور امتیازدهی یک ورودی قابل‌اعتماد ببیند.
"""
from __future__ import annotations

import hashlib
import re
import time

from ..core.models import Job, RawJob
from ..core.text import (canonical_engagement, detect_engagement, normalize_fa,
                         normalize_title, search_key, strip_html)

#: حداکثر طول توضیح ذخیره‌شده — متن کامل آگهی برای امتیازدهی لازم نیست
MAX_DESCRIPTION = 2400

_TAG_CLEAN = re.compile(r"[#\s]+")


def normalize(raw: RawJob, *, now: int | None = None) -> Job:
    """آگهی خام → آگهی یکسان‌شده با انگشت‌نگاشت حذف تکراری."""
    now = int(now if now is not None else time.time())

    title = strip_html(raw.title)
    description = strip_html(raw.description)[:MAX_DESCRIPTION]
    tags = _clean_tags(raw.tags)
    company = strip_html(raw.company)
    location = strip_html(raw.location)
    salary_text = strip_html(raw.salary_text)

    combined = search_key(" ".join(filter(None, [
        title, description, " ".join(tags), raw.employment, salary_text, location,
    ])))

    remote = _is_remote(raw, location, combined)
    # نوع همکاری همیشه یکسان‌شده ذخیره می‌شود؛ منابع عبارت‌هایی مثل
    # ``full_time`` یا ``Full-Time`` می‌فرستند و بدون این مرحله، متن خام
    # انگلیسی به UI می‌رسد و برچسب فارسی پیدا نمی‌کند.
    engagement = (canonical_engagement(raw.employment) if raw.employment
                  else detect_engagement(combined))

    published = raw.published_ts
    if published and published > now + 3600:
        # تاریخ آینده معمولاً یعنی منطقهٔ زمانی اشتباه — به «اکنون» می‌چسبانیم
        published = now

    return Job(
        source=raw.source,
        external_id=raw.external_id,
        title=title,
        company=company,
        url=raw.url,
        description=description,
        tags=tags,
        location=location,
        remote=remote,
        employment=engagement,
        salary_text=salary_text,
        salary_min=raw.salary_min,
        salary_max=raw.salary_max,
        published_ts=published,
        fingerprint=fingerprint(title, company),
    )


def _clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        clean = _TAG_CLEAN.sub(" ", strip_html(tag)).strip()
        key = clean.lower()
        if clean and key not in seen and len(clean) <= 48:
            seen.add(key)
            out.append(clean)
    return out[:12]


def _is_remote(raw: RawJob, location: str, combined: str) -> bool:
    """دورکاری از سه سیگنال: پرچم صریح، محل، و واژه‌ها در متن."""
    if raw.remote is True:
        return True
    loc = location.lower()
    if any(w in loc for w in ("remote", "anywhere", "worldwide", "دورکاری")):
        return True
    return any(w in combined for w in ("دورکاری", "دور کاری", "remote", "anywhere", "از راه دور"))


def fingerprint(title: str, company: str) -> str:
    """کلید یکتایی بین‌منبعی.

    یک آگهی ممکن است هم‌زمان در Remotive و RemoteOK باشد؛ مقایسهٔ عنوان و
    شرکت (بدون وابستگی به منبع) آن دو را یکی می‌کند، در حالی که شناسهٔ
    درون‌منبعی هرگز چنین کاری نمی‌کند.
    """
    material = f"{normalize_title(title)}|{normalize_title(company)}"
    return hashlib.sha1(material.encode("utf-8")).hexdigest()[:20]


def similarity(title_a: str, title_b: str) -> float:
    """شباهت دو عنوان (۰..۱) برای حذف تکراری‌های تقریبی.

    فقط ضریب جاکارد کافی نیست: در عنوان‌های کوتاه، افزودن یک واژه امتیاز را
    به‌شدت می‌اندازد. «Senior Python Developer» و «Senior Python Developer
    (Remote)» جاکارد ۰٫۷۵ می‌گیرند (زیر هر آستانهٔ معقولی) در حالی که هر دو
    یک آگهی‌اند — و همین الگوی «پسوند افزوده‌شده» شایع‌ترین شکل تکرار
    بین‌منبعی است.

    راه‌حل: بیشترین مقدار بین جاکارد و *ضریب پوشش* (اشتراک تقسیم بر
    کوچک‌ترِ دو مجموعه) گرفته می‌شود، ولی ضریب پوشش فقط وقتی معتبر است که
    عنوان کوتاه‌تر دست‌کم سه واژهٔ معنادار داشته باشد. با یک یا دو واژه،
    پوشش تقریباً همیشه ۱ می‌شود و همه‌چیز را در هم می‌آمیزد.
    """
    a = {token for token in normalize_title(title_a).split() if len(token) > 1}
    b = {token for token in normalize_title(title_b).split() if len(token) > 1}
    if not a or not b:
        return 0.0

    intersection = len(a & b)
    jaccard = intersection / len(a | b)
    if min(len(a), len(b)) < 3:
        return jaccard
    return max(jaccard, intersection / min(len(a), len(b)))


__all__ = ["normalize", "fingerprint", "similarity", "MAX_DESCRIPTION",
           "normalize_fa"]
