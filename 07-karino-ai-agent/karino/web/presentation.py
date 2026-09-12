# -*- coding: utf-8 -*-
"""لایهٔ نمایش — تبدیل شناسه‌ها و کلیدهای ماشینی به متن فارسی.

رویدادهای «فعالیت» برای ماشین طراحی شده‌اند: ``kind`` شناسهٔ برنامه‌ای است و
``meta`` کلیدهای انگلیسی دارد (``new``، ``job_id``، ``writer``). نمایش خام
آن‌ها در رابط، هم ناخواناست و هم برای کاربر «ناتمام» به نظر می‌رسد.

قاعده: API همان دادهٔ خام را نگه می‌دارد (کلاینت برنامه‌ای به آن نیاز دارد)،
ولی رابط هرگز شناسه یا کلید انگلیسی و رقم لاتین نشان نمی‌دهد. این ماژول
همان مرز است.
"""
from __future__ import annotations

from ..core.text import fa_number

#: شناسهٔ رویداد → عنوان فارسی
ACTIVITY_KIND_LABELS: dict[str, str] = {
    "boot": "راه‌اندازی",
    "ingest_done": "جمع‌آوری",
    "ingest_empty": "جمع‌آوری بی‌حاصل",
    "ingest_error": "خطای جمع‌آوری",
    "source_error": "خطای منبع",
    "seed_used": "دادهٔ نمونه",
    "score_backfill": "امتیازدهی تکمیلی",
    "proposal_created": "ساخت پیشنهاد",
    "job_saved": "ذخیرهٔ آگهی",
    "job_unsaved": "برداشتن از ذخیره‌شده",
    "scheduler_started": "زمان‌بند",
    "scheduler_error": "خطای زمان‌بند",
    "test": "آزمون",
}

#: کلید فنی ``meta`` → برچسب فارسی. کلید ناشناخته نمایش داده نمی‌شود.
ACTIVITY_META_LABELS: dict[str, str] = {
    "new": "تازه",
    "scored": "امتیازدهی‌شده",
    "fetched": "واکشی‌شده",
    "unique": "یکتا",
    "duplicates": "تکراری",
    "known": "شناخته‌شدهٔ پیشین",
    "source": "منبع",
    "job_id": "شناسهٔ آگهی",
    "writer": "نویسنده",
    "tone": "لحن",
    "variant": "طول",
    "count": "تعداد",
    "env": "محیط اجرا",
    "interval_min": "فاصلهٔ اجرا (دقیقه)",
    "scheduler": "زمان‌بند",
}

#: مقدارهای شمارشی → معادل فارسی
META_VALUE_LABELS: dict[str, str] = {
    "rule_based": "قاعده‌محور",
    "llm": "مدل زبانی",
    "development": "توسعه",
    "production": "تولید",
    "test": "آزمون",
    "seed": "نمونهٔ آفلاین",
    "formal": "رسمی و حرفه‌ای",
    "concise": "کوتاه و مستقیم",
    "consultative": "مشورتی و همکارانه",
    "standard": "استاندارد",
    "short": "کوتاه",
}


def kind_label(kind: str) -> str:
    """عنوان فارسی رویداد، یا خود شناسه اگر ناشناخته باشد (هرگز خالی نمی‌ماند)."""
    return ACTIVITY_KIND_LABELS.get(kind, kind or "رویداد")


def env_label(env: str | None) -> str:
    """نام محیط اجرا به فارسی — نشان «development» در رابط ناتمام به نظر می‌رسد."""
    value = (env or "").strip().lower()
    if not value:
        return "نامشخص"
    return META_VALUE_LABELS.get(value, env or value)


def meta_pairs(meta: dict | None) -> list[tuple[str, str]]:
    """جفت‌های (برچسب فارسی، مقدار فارسی) برای نمایش.

    کلیدهای ناشناخته حذف می‌شوند: پیام رویداد معنای اصلی را می‌رساند و
    نمایش یک کلید انگلیسی، رابط را ناتمام نشان می‌دهد.
    """
    pairs: list[tuple[str, str]] = []
    for key, value in (meta or {}).items():
        label = ACTIVITY_META_LABELS.get(key)
        if not label:
            continue
        pairs.append((label, meta_value(value)))
    return pairs


def meta_value(value) -> str:
    """مقدار ``meta`` → متن نمایشی فارسی (بدون رقم لاتین)."""
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    if isinstance(value, int):
        return fa_number(value)
    if isinstance(value, float):
        return fa_number(value)
    text = str(value)
    return META_VALUE_LABELS.get(text, text)


__all__ = ["ACTIVITY_KIND_LABELS", "ACTIVITY_META_LABELS", "META_VALUE_LABELS",
           "kind_label", "meta_pairs", "meta_value", "env_label"]
