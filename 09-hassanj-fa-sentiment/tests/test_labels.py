# -*- coding: utf-8 -*-
"""آزمون برچسب‌ها و قالب‌بندی اعداد فارسی.

هر عددی که به کاربر می‌رسد از ``labels`` می‌گذرد. اگر اینجا رقم لاتین یا ممیز
لاتین بیرون بیاید، همهٔ صفحه‌ها ناهمخوان می‌شوند — پس همین‌جا قفل می‌شود.
"""
from __future__ import annotations

import pytest

from hassanj.config import CONFIDENCE_HIGH, CONFIDENCE_LOW, LABELS
from hassanj.labels import (band_label, confidence_band, fa_datetime, fa_number,
                            fa_percent, sentiment_label, sentiment_slug,
                            to_persian_digits, verdict_sentence)

LATIN_DIGITS = set("0123456789")


def test_persian_digits_replaces_latin():
    assert to_persian_digits("1404/05/21") == "۱۴۰۴/۰۵/۲۱"
    assert to_persian_digits(98) == "۹۸"


@pytest.mark.parametrize("value,expected", [
    (0, "۰"),
    (7, "۷"),
    (1404, "۱٬۴۰۴"),
    (1234567, "۱٬۲۳۴٬۵۶۷"),
    (12.4, "۱۲"),          # بدون اعشار، گرد می‌شود
])
def test_fa_number_integer_paths(value, expected):
    kwargs = {} if isinstance(value, int) else {"decimals": 0}
    assert fa_number(value, **kwargs) == expected


def test_fa_number_decimals_use_persian_separators():
    result = fa_number(1234.56, decimals=1)
    assert result == "۱٬۲۳۴٫۶"
    assert "." not in result and "," not in result


def test_fa_percent_sign_and_scale():
    assert fa_percent(0.5) == "۵۰٫۰٪"
    assert fa_percent(0.987, decimals=0) == "۹۹٪"


def test_fa_percent_signed_uses_persian_minus():
    assert fa_percent(0.1, signed=True).startswith("+")
    negative = fa_percent(-0.1, signed=True)
    assert negative.startswith("−")           # U+2212، نه خط تیرهٔ لاتین
    assert "-" not in negative


def test_no_latin_digit_leaks_from_formatters():
    samples = [fa_number(1234.5678, decimals=3), fa_percent(0.1234),
               fa_datetime("2026-09-13 20:39")]
    for sample in samples:
        assert not (set(sample) & LATIN_DIGITS), sample


def test_fa_datetime_handles_missing_value():
    assert fa_datetime(None) == "—"
    assert fa_datetime("") == "—"


def test_every_label_has_persian_name():
    for code in LABELS:
        assert sentiment_label(code) != code
        assert all(ord(char) > 128 for char in sentiment_label(code))


def test_sentiment_slug_is_latin_only():
    for code in LABELS:
        assert sentiment_slug(code).isascii()


# ------------------------------------------------------------------ باند اطمینان
@pytest.mark.parametrize("confidence,expected", [
    (0.99, "high"),
    (CONFIDENCE_HIGH, "high"),
    (CONFIDENCE_HIGH - 0.01, "medium"),
    (CONFIDENCE_LOW, "medium"),
    (CONFIDENCE_LOW - 0.01, "low"),
    (0.0, "low"),
])
def test_confidence_band_boundaries(confidence, expected):
    assert confidence_band(confidence) == expected


def test_band_labels_are_descriptive_not_numeric():
    for band in ("high", "medium", "low"):
        assert band_label(band) not in ("بالا", "متوسط", "پایین")


def test_verdict_never_claims_certainty_when_low():
    sentence = verdict_sentence("pos", 0.31, "low")
    assert "قطعی نگیرید" in sentence
    assert "مثبت" in sentence


def test_verdict_sentence_differs_per_band():
    sentences = {verdict_sentence("pos", 0.9, "high"),
                 verdict_sentence("pos", 0.6, "medium"),
                 verdict_sentence("pos", 0.3, "low")}
    assert len(sentences) == 3
