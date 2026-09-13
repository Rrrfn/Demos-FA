# -*- coding: utf-8 -*-
"""بازهٔ تاریخی — تعریف «نیمهٔ اول و دوم» و سطل‌های نمودار روند.

این فایل یک باگ واقعی را می‌بندد: کارت شاخص و بینش رشد، هر کدام نیمه‌ها را
جور دیگری می‌بریدند (یکی بر حسب شمار سطل‌های نمودار، یکی بر حسب شمار ردیف)،
و روی یک صفحه دو عدد متفاوت برای یک ادعا نشان می‌دادند. آزمون‌های اینجا همان
یک‌مرجعی را قفل می‌کنند.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from reportsaz.analytics import (_trend_series, analyse, period_growth,
                                 range_split)
from reportsaz.cleaning import CleanOptions, clean
from reportsaz.ingest.cells import jalali_to_gregorian
from reportsaz.labels import fa_date_label, gregorian_to_jalali
from reportsaz.profile import profile_frame


# ------------------------------------------------------------------ مرز نیمه
def test_range_split_is_the_middle_of_the_span_not_of_the_rows():
    """ردیف‌ها همه در ابتدای بازه‌اند؛ مرز باید وسط *زمان* بماند."""
    dates = pd.Series([dt.date(2024, 1, 1)] * 50 + [dt.date(2024, 1, 31)] * 2)
    split = range_split(dates)
    assert split == dt.date(2024, 1, 16)


def test_range_split_needs_two_distinct_dates():
    assert range_split(pd.Series([dt.date(2024, 1, 1)] * 5)) is None
    assert range_split(pd.Series([None, None])) is None


def test_period_growth_ignores_where_the_rows_are_clustered():
    """همهٔ ردیف‌های پرمقدار در نیمهٔ اول‌اند؛ رشد باید منفی باشد.

    تقسیم بر شمار ردیف، بیشتر ردیف‌ها را در «نیمهٔ اول» می‌گذاشت و نتیجه را
    بی‌معنا می‌کرد.
    """
    early = [dt.date(2024, 1, day) for day in range(1, 6)]
    late = [dt.date(2024, 1, day) for day in range(25, 32)]
    table = pd.DataFrame({
        "date": early * 20 + late * 2,
        "value": [1000.0] * (len(early) * 20) + [50.0] * (len(late) * 2),
    })
    growth = period_growth(table["date"], table["value"])
    assert growth is not None
    recent, previous, ratio = growth
    assert previous == pytest.approx(100_000.0)
    assert recent == pytest.approx(700.0)
    assert ratio < 0


def test_period_growth_needs_enough_samples():
    table = pd.DataFrame({"date": [dt.date(2024, 1, 1), dt.date(2024, 1, 5)],
                          "value": [1.0, 2.0]})
    assert period_growth(table["date"], table["value"]) is None


def test_kpi_change_and_growth_insight_never_disagree(frame):
    """رگرسیون باگ اصلی: یک ادعا، یک عدد."""
    cleaned = clean(frame, CleanOptions()).frame
    analysis = analyse(cleaned, profile_frame(cleaned),
                       metric="مبلغ فروش", dimension="منطقه",
                       date_column="تاریخ")
    total = next((kpi for kpi in analysis.kpis if kpi.key == "total"), None)
    insight = next((item for item in analysis.insights
                    if item.key == "growth"), None)
    assert total is not None and insight is not None
    assert insight.evidence["ratio"] >= 0 if total.direction == "up" else \
        insight.evidence["ratio"] < 0
    #: همان نسبت، همان دو نیمه — نه دو محاسبهٔ مستقل.
    assert total.change.startswith(_percent_text(insight.evidence["ratio"]))


def _percent_text(ratio: float) -> str:
    """همان متنی که در کارت شاخص می‌آید، برای مقایسه."""
    from reportsaz.labels import fa_percent

    return fa_percent(abs(ratio))


def test_growth_comes_from_all_rows_not_from_chart_points(frame):
    """جمع دو نیمه باید با جمع کل جدول بخواند، نه با جمع سطل‌های نمودار."""
    cleaned = clean(frame, CleanOptions()).frame
    analysis = analyse(cleaned, profile_frame(cleaned),
                       metric="مبلغ فروش", date_column="تاریخ")
    insight = next(item for item in analysis.insights if item.key == "growth")
    values = pd.to_numeric(cleaned["مبلغ فروش"], errors="coerce")
    assert (insight.evidence["recent"] + insight.evidence["previous"]
            == pytest.approx(float(values.sum())))


# ------------------------------------------------------------------ سطل‌ها
def test_trend_labels_are_jalali_dates(frame):
    cleaned = clean(frame, CleanOptions()).frame
    series = _trend_series(cleaned, "تاریخ", "مبلغ فروش")
    assert series.points
    for point in series.points:
        assert point.label.startswith("۱۴")
        assert "/" in point.label
        assert not any(char.isascii() and char.isdigit() for char in point.label)


def test_buckets_start_at_the_first_row_of_data(frame):
    """سطل نخست باید از خودِ داده شروع شود، نه از مرز تقویم."""
    cleaned = clean(frame, CleanOptions()).frame
    from reportsaz.ingest.cells import parse_date

    first = min(date for date in cleaned["تاریخ"].map(parse_date)
                if date is not None)
    series = _trend_series(cleaned, "تاریخ", "مبلغ فروش")
    assert series.points[0].label == fa_date_label(first)


def test_partial_trailing_bucket_is_dropped_and_explained():
    """بازهٔ ۱۰۱ روزه با گام هفتگی: ۱۴ سطل کامل و ۳ روز باقی‌مانده."""
    dates = [dt.date(2024, 3, 20) + dt.timedelta(days=offset)
             for offset in range(101)]
    table = pd.DataFrame({"date": dates, "value": [1.0] * 101})
    series = _trend_series(table, "date", "value")
    assert series.unit == "هفته"
    assert len(series.points) == 14
    assert series.note
    assert series.total == pytest.approx(98.0)


def test_even_span_keeps_every_bucket_and_says_nothing():
    """بازهٔ ۳۶۴ روزه دقیقاً ۵۲ هفته است؛ نباید چیزی حذف شود."""
    dates = [dt.date(2024, 3, 20) + dt.timedelta(days=offset)
             for offset in range(364)]
    table = pd.DataFrame({"date": dates, "value": [1.0] * 364})
    series = _trend_series(table, "date", "value")
    assert len(series.points) == 52
    assert series.note == ""
    assert series.total == pytest.approx(364.0)


def test_short_span_is_daily_and_never_trimmed():
    dates = [dt.date(2024, 3, 20) + dt.timedelta(days=offset)
             for offset in range(20)]
    table = pd.DataFrame({"date": dates, "value": [1.0] * 20})
    series = _trend_series(table, "date", "value")
    assert series.unit == "روز"
    assert len(series.points) == 20
    assert series.note == ""


def test_long_span_unit_names_what_it_actually_does():
    """سطل ۳۰ روزه «ماه» نیست؛ ادعای نادرست نباید روی نمودار برود."""
    dates = [dt.date(2024, 1, 1) + dt.timedelta(days=offset)
             for offset in range(500)]
    table = pd.DataFrame({"date": dates, "value": [1.0] * 500})
    series = _trend_series(table, "date", "value")
    assert series.unit == "بازهٔ ۳۰روزه"
    assert "ماه" not in series.unit


# ------------------------------------------------------------------ تقویم
def test_gregorian_to_jalali_is_the_exact_inverse_of_the_parser():
    """تبدیل معکوس باید روز‌به‌روز با تبدیل سمت ورود داده بخواند."""
    day = dt.date(2015, 1, 1)
    while day < dt.date(2035, 1, 1):
        converted = gregorian_to_jalali(day.year, day.month, day.day)
        assert converted is not None
        assert jalali_to_gregorian(*converted) == (day.year, day.month, day.day)
        day += dt.timedelta(days=1)


def test_new_year_boundaries_are_not_off_by_one():
    assert fa_date_label("2024-03-20") == "۱۴۰۳/۰۱/۰۱"
    assert fa_date_label("2025-03-21") == "۱۴۰۴/۰۱/۰۱"


def test_date_label_falls_back_to_raw_text():
    """چیزی که تاریخ نیست نباید تاریخ ساختگی بگیرد."""
    assert fa_date_label("بازهٔ نامعلوم") == "بازهٔ نامعلوم"
    assert fa_date_label("") == ""
