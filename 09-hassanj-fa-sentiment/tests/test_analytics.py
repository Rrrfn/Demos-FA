# -*- coding: utf-8 -*-
"""آزمون لایهٔ تحلیل — عددها، توزیع‌ها و جدایی واقعی از پیش‌بینی‌شده.

دو قاعده اینجا قفل می‌شود:

۱) ترکیب **واقعی** دیتاست و ترکیب **پیش‌بینی‌شدهٔ** مدل دو چیز جدا هستند و
   قاطی نمی‌شوند.

۲) لایهٔ تحلیل عدد خام برمی‌گرداند و قالب‌بندی نمی‌کند؛ قالب‌بندی کار لایهٔ
   نمایش است. اگر این مرز بشکند، مصرف‌کنندهٔ دیگری هم مجبور است همان قالب را
   بپذیرد.
"""
from __future__ import annotations

import re

import pytest

from hassanj import analytics
from hassanj.config import LABELS, TREND_MONTHS

LATIN_DIGITS = re.compile(r"[0-9]")


# ------------------------------------------------------------------ ترکیب کلاس‌ها
def test_actual_mix_is_balanced(fast_env):
    mix = analytics.actual_mix(fast_env["frame"])
    assert mix["total"] == len(fast_env["frame"])
    assert set(mix["counts"]) == set(LABELS)
    assert abs(sum(mix["shares"].values()) - 1.0) < 1e-3
    assert len(set(mix["counts"].values())) == 1        # توازن دقیق


def test_predicted_mix_covers_every_sample(pipeline, fast_env):
    texts = [str(text) for text in fast_env["frame"]["text"]]
    mix = analytics.predicted_mix(pipeline, texts)
    assert mix["total"] == len(texts)
    assert sum(mix["counts"].values()) == len(texts)
    assert abs(sum(mix["shares"].values()) - 1.0) < 1e-3


def test_predicted_mix_reports_confidence_bands(pipeline, fast_env):
    texts = [str(text) for text in fast_env["frame"]["text"]]
    bands = analytics.predicted_mix(pipeline, texts)["band_counts"]
    assert set(bands) == {"high", "medium", "low"}
    assert sum(bands.values()) == len(texts)


def test_comparison_is_per_class_and_bounded(pipeline, fast_env):
    rows = analytics.comparison(pipeline, fast_env["frame"])
    assert [row["code"] for row in rows] == list(LABELS)
    for row in rows:
        assert 0.0 <= row["actual"] <= 1.0
        assert 0.0 <= row["predicted"] <= 1.0
        assert row["label"] != row["code"]       # برچسب فارسی است، نه کد لاتین


# ------------------------------------------------------------------ روند و ماهیت
def test_monthly_mix_uses_the_declared_windows(fast_env):
    """دسته‌بندی باید روی پنجره‌های اعلام‌شده باشد، نه روی ماه میلادی.

    رگرسیون: یک بار روی ماه میلادی گروه‌بندی شد و هفت سطل ساخت — چون مرزهای
    میلادی با مرزهای پنجرهٔ دیتاست یکی نیستند — و برچسب سطل هفتم رقم لاتین
    به رابط می‌ریخت.
    """
    from hassanj.dataset import MONTH_NAMES

    rows = analytics.monthly_mix(fast_env["frame"])
    assert len(rows) == TREND_MONTHS == len(MONTH_NAMES)
    assert [row["title"] for row in rows] == list(MONTH_NAMES)
    assert sum(row["total"] for row in rows) == len(fast_env["frame"])
    for row in rows:
        assert abs(sum(row["shares"].values()) - 1.0) < 1e-3
        assert row["total"] > 0
        assert not LATIN_DIGITS.search(row["title"]), row["title"]


def test_monthly_mix_without_date_column_returns_empty(fast_env):
    frame = fast_env["frame"].drop(columns=["date"])
    assert analytics.monthly_mix(frame) == []


def test_declared_trend_is_a_valid_composition():
    from hassanj.dataset import MONTH_NAMES

    rows = analytics.declared_trend()
    assert len(rows) == TREND_MONTHS
    assert [row["title"] for row in rows] == list(MONTH_NAMES)
    for index, row in enumerate(rows):
        assert row["month"] == index + 1
        assert set(row["shares"]) == set(LABELS)
        assert abs(sum(row["shares"].values()) - 1.0) < 1e-3
        assert row["total"] > 0
        assert not LATIN_DIGITS.search(row["title"])


def test_declared_trend_reflects_class_balance():
    """در جدول اعلام‌شده هم باید توازن کلاس‌ها دیده شود.

    سهم هر کلاس در مجموع شش ماه باید نزدیک یک‌سوم باشد؛ رگرسیون: نسخهٔ
    پیشین وزن‌های جدول را مستقیم به‌عنوان ترکیب ماهانه گزارش می‌کرد و سهم
    مثبت را ۰٫۴۰ نشان می‌داد در حالی که دیتاست هرگز آن را تولید نمی‌کند.
    """
    rows = analytics.declared_trend()
    totals = {code: sum(row["counts"][code] for row in rows) for code in LABELS}
    assert len(set(totals.values())) == 1
    for code, count in totals.items():
        share = count / sum(totals.values())
        assert abs(share - 1 / 3) < 0.02, (code, share)


def test_measured_trend_matches_the_declared_trend(fast_env):
    """روند محاسبه‌شده باید روی جدول اعلام‌شده بیفتد.

    همین هم ادعای بازتولیدپذیری صفحهٔ متدولوژی است: اگر نمودار محاسبه‌شده با
    جدول نخواند، جایی از ساخت دیتاست مشکل دارد.
    """
    measured = analytics.monthly_mix(fast_env["frame"])
    declared = analytics.declared_trend(per_class=len(fast_env["frame"]) // 3)
    assert len(measured) == len(declared)
    for row, table in zip(measured, declared):
        assert row["title"] == table["title"]
        assert row["counts"] == table["counts"]
        for code in LABELS:
            assert abs(row["shares"][code] - table["shares"][code]) < 1e-4


# ---------------------------------------------------------------------- توزیع‌ها
def test_confidence_histogram_bins_and_total(pipeline, fast_env):
    texts = [str(text) for text in fast_env["frame"]["text"]]
    points = analytics.confidence_histogram(pipeline, texts, bins=10)
    assert len(points) == 10
    assert sum(count for _, count in points) == len(texts)
    centres = [centre for centre, _ in points]
    assert centres == sorted(centres)
    assert 0 <= centres[0] <= centres[-1] <= 100


def test_confidence_histogram_on_empty_input(pipeline):
    assert analytics.confidence_histogram(pipeline, []) == []


def test_length_histogram_counts_every_row(fast_env):
    points = analytics.length_histogram(fast_env["frame"])
    assert sum(count for _, count in points) == len(fast_env["frame"])


# ---------------------------------------------------------------------- واژگان
def test_class_terms_are_disjoint_and_positive(pipeline):
    terms = analytics.class_terms(pipeline)
    assert {"pos", "neg"} <= set(terms) <= set(LABELS)
    positive = {item["term"] for item in terms["pos"]}
    negative = {item["term"] for item in terms["neg"]}
    assert positive and negative
    assert not positive & negative
    for rows in terms.values():
        scores = [item["score"] for item in rows]
        assert scores == sorted(scores, reverse=True)


def test_unknown_terms_are_absent_from_vocabulary(pipeline, fast_env):
    from hassanj.model import vocabulary

    known = vocabulary(pipeline)
    for row in analytics.unknown_terms(fast_env["frame"], pipeline, k=8):
        assert row["term"] not in known
        assert 0.0 <= row["share"] <= 1.0


# ------------------------------------------------------------------ کارت‌های شاخص
def test_summary_returns_raw_numbers_not_formatted_strings(pipeline, fast_env):
    """رگرسیون: این کارت‌ها یک بار رشتهٔ آمادهٔ فارسی برمی‌گرداندند.

    آن کار، قالب‌بندی را داخل لایهٔ تحلیل می‌برد و مرز لایه‌ها را می‌شکست.
    الان باید عدد خام باشد تا لایهٔ نمایش تصمیم بگیرد.
    """
    metrics = fast_env["metrics"]
    result = analytics.summary(fast_env["frame"], pipeline, metrics)
    assert set(result) >= {"n_samples", "vocabulary_size", "mean_length", "class_count"}
    for key, value in result.items():
        assert isinstance(value, (int, float)), key
        assert not LATIN_DIGITS.match(str(value)) or isinstance(value, (int, float))
        assert not isinstance(value, str), key
    assert result["n_samples"] == len(fast_env["frame"])
    assert result["class_count"] == len(LABELS)
    assert result["vocabulary_size"] == metrics["vocabulary_size"]
