# -*- coding: utf-8 -*-
"""آزمون‌های ابزار متن فارسی.

چون تمام تطبیق مهارت روی خروجی همین توابع سوار است، یک اشتباه در
یکسان‌سازی مستقیماً امتیازها را خراب می‌کند — پس این‌ها حساس‌ترین تست‌ها
هستند.
"""
from __future__ import annotations

import time

from karino.core.text import (canonical_engagement, compact, detect_engagement,
                              detect_seniority, fa_delta, fa_number,
                              freshness_band, normalize_fa, normalize_title,
                              relative_time, search_key, strip_html)


def test_strip_html_removes_tags_and_decodes_entities():
    assert strip_html("<p>سلام &amp; خوش آمدید</p>") == "سلام & خوش آمدید"
    assert strip_html("<script>evil()</script>متن") == "متن"
    assert strip_html("<style>a{}</style>متن") == "متن"
    assert strip_html(None) == ""


def test_normalize_fa_unifies_arabic_letters():
    """ی و ک عربی باید به شکل فارسی برگردند، وگرنه تطبیق واژه‌ها می‌شکند."""
    assert normalize_fa("علي") == normalize_fa("علی")
    assert normalize_fa("كيفيت") == normalize_fa("کیفیت")


def test_normalize_fa_collapses_zero_width_and_spaces():
    """نیم‌فاصله به فاصلهٔ معمولی بدل می‌شود تا «دورکاری» و «دور کاری» یکی شوند."""
    assert normalize_fa("دور\u200cکاری") == normalize_fa("دور کاری")
    assert normalize_fa("a    b") == "a b"


def test_normalize_fa_makes_digits_latin_for_matching():
    """اعداد برای تطبیق یکسان می‌شوند — چه فارسی، چه عربی، چه لاتین."""
    assert normalize_fa("۴G") == "4G"
    assert normalize_fa("٤G") == "4G"
    assert normalize_fa("4G") == "4G"


def test_search_key_is_lowercase_and_clean():
    assert search_key("<b>Python</b> و Flask") == "python و flask"


def test_compact_respects_word_boundary():
    text = "واژه " * 100
    result = compact(text, limit=40)
    assert result.endswith("…")
    assert len(result) <= 42


def test_fa_number_uses_persian_digits():
    assert fa_number(1234) == "۱٬۲۳۴"
    assert fa_number(0) == "۰"
    assert fa_number(None) == "—"


def test_fa_number_without_grouping_for_identifiers():
    """شناسه‌ها نباید جداکنندهٔ هزارگان بگیرند، وگرنه مقدار عوض می‌شود."""
    assert fa_number(1234, group=False) == "۱۲۳۴"


def test_fa_delta_signs():
    assert fa_delta(5) == "＋۵"
    assert fa_delta(-3) == "−۳"
    assert fa_delta(0) == "۰"


def test_no_latin_digits_leak_into_display_strings():
    """قاعدهٔ محصول: متن نمایشی هیچ رقم لاتینی ندارد."""
    values = [fa_number(987654), fa_delta(-42), relative_time(int(time.time()) - 7200)]
    for value in values:
        assert not any(ch.isdigit() and ch.isascii() for ch in value), value


def test_relative_time_buckets():
    now = 1_800_000_000
    assert relative_time(now - 30, now=now) == "همین حالا"
    assert "دقیقه" in relative_time(now - 600, now=now)
    assert "ساعت" in relative_time(now - 7200, now=now)
    assert "روز" in relative_time(now - 3 * 86_400, now=now)
    assert relative_time(None) == "نامشخص"


def test_freshness_bands():
    now = 1_800_000_000
    assert freshness_band(now - 3600, now=now) == "fresh"
    assert freshness_band(now - 5 * 86_400, now=now) == "recent"
    assert freshness_band(now - 15 * 86_400, now=now) == "aging"
    assert freshness_band(now - 60 * 86_400, now=now) == "stale"
    assert freshness_band(None, now=now) == "unknown"


def test_detect_seniority_prefers_strongest_signal():
    assert detect_seniority("senior python developer") == "senior"
    assert detect_seniority("توسعه‌دهندهٔ ارشد پایتون") == "senior"
    assert detect_seniority("junior developer") == "junior"
    assert detect_seniority("برنامه‌نویس") == "unknown"


def test_detect_engagement():
    assert detect_engagement("پروژه‌ای و دورکاری") == "freelance"
    assert detect_engagement("تمام وقت در دفتر") == "fulltime"
    assert detect_engagement("کارآموز برنامه‌نویسی") == "internship"
    assert detect_engagement("نیاز به نیرو") == "unknown"


def test_canonical_engagement_maps_source_variants():
    """شکل‌های ناهمگون منابع باید به کلید استاندارد یکی شوند.

    منابع ``full_time`` می‌فرستند و دیگری ``Full-Time``؛ اگر این‌ها یکی
    نشوند، برچسب فارسی پیدا نمی‌کنند و متن خام انگلیسی در رابط می‌ماند.
    """
    assert canonical_engagement("full_time") == "fulltime"
    assert canonical_engagement("Full-Time") == "fulltime"
    assert canonical_engagement("permanent") == "fulltime"
    assert canonical_engagement("Contract") == "freelance"
    assert canonical_engagement("Part-time") == "freelance"
    assert canonical_engagement("INTERN") == "internship"


def test_canonical_engagement_returns_only_labelable_keys():
    """هر خروجی باید کلید برچسب فارسی باشد، وگرنه رابط متن خام نشان می‌دهد."""
    from karino.core.models import ENGAGEMENT_LABELS

    for raw in ("full_time", "contract", "intern", "", None, "  ", "شیفت شب"):
        assert canonical_engagement(raw) in ENGAGEMENT_LABELS, raw


def test_normalize_title_strips_punctuation():
    assert normalize_title("Senior Python Developer (Remote)!") == "senior python developer remote"
