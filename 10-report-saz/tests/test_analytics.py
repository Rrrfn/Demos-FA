# -*- coding: utf-8 -*-
"""موتور تحلیل — شاخص، بینش، ناهنجاری، نوسان و همبستگی.

بیشتر این آزمون‌ها یک چیز را می‌سنجند: **صداقت در نبود داده.** سخت‌ترین بخش
این ماژول تولید عدد نیست، *تولید نکردن* عدد است وقتی داده‌اش نیست.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportsaz.analytics import (MIN_SAMPLES, analyse, correlation,
                                 detect_anomalies, movers)
from reportsaz.cleaning import CleanOptions, clean
from reportsaz.profile import profile_frame


def _pipeline(frame):
    """جدول را پاک‌سازی، پروفایل و تحلیل می‌کند — مثل مسیر واقعی محصول."""
    cleaned = clean(frame, CleanOptions())
    profile = profile_frame(cleaned.frame)
    return cleaned.frame, profile, analyse(cleaned.frame, profile)


# ------------------------------------------------------------------ شاخص
def test_kpis_come_from_the_metric_column(messy_frame):
    frame, _profile, analysis = _pipeline(messy_frame)
    values = pd.to_numeric(frame["مبلغ فروش"], errors="coerce")
    by_key = {kpi.key: kpi for kpi in analysis.kpis}
    assert by_key["total"].raw == pytest.approx(float(values.sum()))
    assert by_key["mean"].raw == pytest.approx(float(values.mean()))
    assert by_key["max"].raw == pytest.approx(float(values.max()))
    assert by_key["median"].raw == pytest.approx(float(values.median()))


def test_kpi_values_are_persian_digits(messy_frame):
    _frame, _profile, analysis = _pipeline(messy_frame)
    for kpi in analysis.kpis:
        assert not any(char.isdigit() and char.isascii()
                       for char in kpi.value), kpi.value


def test_no_metric_still_reports_row_count(text_only_frame):
    """جدول بدون ستون عددی نباید کارت جعلی بسازد."""
    _frame, _profile, analysis = _pipeline(text_only_frame)
    keys = {kpi.key for kpi in analysis.kpis}
    assert "total" not in keys and "mean" not in keys
    assert "rows" in keys
    assert any("متریک" in note for note in analysis.notes)


def test_growth_uses_two_halves_not_last_two_rows(frame):
    """رشد باید جمع دو نیمهٔ بازه را مقایسه کند، نه دو سطر آخر را."""
    _frame, _profile, analysis = _pipeline(frame)
    total = next((kpi for kpi in analysis.kpis if kpi.key == "total"), None)
    trend = analysis.series_by_key("trend")
    assert total is not None and trend is not None
    if total.change:
        assert total.direction in ("up", "down")
        assert total.change.endswith("٪")


# ------------------------------------------------------------------ روند
def test_trend_has_points_from_real_dates(frame):
    _frame, _profile, analysis = _pipeline(frame)
    trend = analysis.series_by_key("trend")
    assert trend is not None and trend.points
    assert trend.kind == "line"
    assert all(point.value >= 0 for point in trend.points)


def test_no_date_column_reports_reason_not_fake_trend(wide_frame):
    _frame, _profile, analysis = _pipeline(wide_frame)
    trend = analysis.series_by_key("trend")
    assert trend is not None
    assert trend.points == []
    assert trend.empty_reason
    assert any("تاریخ" in note for note in analysis.notes)


def test_tiny_frame_does_not_invent_a_trend(tiny_frame):
    _frame, _profile, analysis = _pipeline(tiny_frame)
    trend = analysis.series_by_key("trend")
    assert trend is None or not trend.points


# ------------------------------------------------------------------ توزیع
def test_distribution_edges_stay_inside_the_real_range():
    """محور توزیع نباید از محدودهٔ واقعی داده بیرون بزند.

    ``pd.cut`` لبهٔ نخستین بازه را کمی پایین‌تر از کمترین مقدار باز می‌کند؛
    روی ستون مبلغ این یعنی برچسبی مثل «−۱٬۴۱۹٬۵۴۱ تا …» که در داده وجود
    ندارد.
    """
    values = [120_000 + index * 4_100 + (index % 7) * 900 for index in range(120)]
    frame = pd.DataFrame({"مبلغ": values})
    _frame, _profile, analysis = _pipeline(frame)
    distribution = analysis.series_by_key("distribution")
    assert distribution is not None and distribution.points
    lowest, highest = min(values), max(values)
    for point in distribution.points:
        for bound in point.label.split(" تا "):
            number = int(bound.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
                         .replace("٬", "").replace("−", "-"))
            assert lowest <= number <= highest, point.label


# ------------------------------------------------------------------ تفکیک
def test_breakdown_sums_to_its_own_total(messy_frame):
    """جمع گروه‌ها باید با جمع اعلام‌شدهٔ همان تفکیک بخواند.

    سطرهایی که ستون گروهشان خالی است قابل نسبت‌دادن به هیچ گروهی نیستند؛
    جدا شمرده می‌شوند تا «گم شدن» عدد را وانمود نکنند.
    """
    frame, _profile, analysis = _pipeline(messy_frame)
    breakdown = analysis.breakdowns[0]
    assert sum(row["value"] for row in breakdown.rows) == \
        pytest.approx(breakdown.total)
    if breakdown.dropped:
        #: پس از پاک‌سازی، سلول خالی به NaN تبدیل شده؛ فیلتر باید با ``notna``
        #: باشد نه با مقایسهٔ رشته‌ای، وگرنه "nan" به‌عنوان گروه شمرده می‌شود.
        labelled = frame[frame[breakdown.dimension].notna()]
        total = pd.to_numeric(labelled[breakdown.metric], errors="coerce").sum()
        assert breakdown.total == pytest.approx(total)


def test_breakdown_shares_are_ratios(messy_frame):
    _frame, _profile, analysis = _pipeline(messy_frame)
    for row in analysis.breakdowns[0].rows:
        assert 0 <= row["share"] <= 1
        assert row["share_text"].endswith("٪")


def test_dimension_ranking_is_descending(messy_frame):
    _frame, _profile, analysis = _pipeline(messy_frame)
    values = [row["value"] for row in analysis.breakdowns[0].rows]
    assert values == sorted(values, reverse=True)


# ------------------------------------------------------------------ بینش‌ها
def test_every_insight_carries_evidence(messy_frame):
    """هیچ بینشی بدون شاهد عددی ساخته نمی‌شود."""
    _frame, _profile, analysis = _pipeline(messy_frame)
    assert analysis.insights
    for insight in analysis.insights:
        assert insight.evidence, insight.key
        assert insight.title.strip() and insight.body.strip()


def test_concentration_insight_matches_the_breakdown(messy_frame):
    _frame, _profile, analysis = _pipeline(messy_frame)
    insight = next((item for item in analysis.insights
                    if item.key == "concentration"), None)
    assert insight is not None
    top = analysis.breakdowns[0].rows[0]
    assert insight.evidence["label"] == top["label"]
    assert insight.evidence["share"] == pytest.approx(top["share"])


def test_no_insights_when_there_is_nothing_to_say(text_only_frame):
    _frame, _profile, analysis = _pipeline(text_only_frame)
    assert not any(item.key == "concentration" for item in analysis.insights)


# ------------------------------------------------------------------ ناهنجاری
def test_iqr_flags_a_real_outlier():
    frame = pd.DataFrame({"مبلغ": [100, 102, 98, 101, 99, 103, 97, 100,
                                   104, 50_000]})
    profile = profile_frame(frame)
    found = detect_anomalies(frame, profile)
    assert found
    assert any(item.value == 50_000 for item in found)
    assert all(item.reason.strip() for item in found)


def test_anomalies_are_sorted_by_score():
    frame = pd.DataFrame({"مبلغ": [100, 101, 102, 103, 104, 105, 106, 107,
                                   -5_000, 99_000]})
    found = detect_anomalies(frame, profile_frame(frame))
    scores = [item.score for item in found]
    assert scores == sorted(scores, reverse=True)


def test_too_few_samples_produces_no_anomalies():
    """زیر حداقل نمونه، «ناهنجاری» فقط نوسان تصادفی است."""
    frame = pd.DataFrame({"مبلغ": [1, 2, 1000]})
    assert len(frame) < MIN_SAMPLES
    assert detect_anomalies(frame, profile_frame(frame)) == []


def test_anomalies_are_flagged_not_removed():
    frame = pd.DataFrame({"مبلغ": [100, 101, 102, 103, 104, 105, 106, 9_999]})
    cleaned = clean(frame, CleanOptions())
    assert 9_999 in set(cleaned.frame["مبلغ"])


# ------------------------------------------------------------------ همبستگی
def _noisy(values, factor: int = 7, offset: int = 0) -> list[float]:
    """مقدارهای غیرترتیبی — وگرنه پروفایل آن‌ها را شناسه می‌بیند و متریک
    نمی‌شوند (که رفتار درستی است)."""
    return [value * 1.0 + (value % factor) * 3 + offset for value in values]


def test_correlation_of_identical_columns_is_one():
    values = _noisy(range(20))
    frame = pd.DataFrame({"مبلغ الف": values, "مبلغ ب": values})
    result = correlation(frame, profile_frame(frame))
    assert result["columns"]
    assert result["matrix"][0][1] == pytest.approx(1.0)


def test_correlation_of_opposite_columns_is_minus_one():
    values = _noisy(range(20))
    frame = pd.DataFrame({"مبلغ الف": values,
                          "مبلغ ب": [-value for value in values]})
    result = correlation(frame, profile_frame(frame))
    assert result["matrix"][0][1] == pytest.approx(-1.0)


def test_correlation_needs_two_metrics():
    frame = pd.DataFrame({"مبلغ": _noisy(range(20))})
    result = correlation(frame, profile_frame(frame))
    assert result["columns"] == []
    assert result["note"]


def test_correlation_handles_missing_values_with_a_note():
    values = _noisy(range(20))
    second = list(values)
    second[3] = None
    frame = pd.DataFrame({"مبلغ الف": values, "مبلغ ب": second})
    result = correlation(frame, profile_frame(frame))
    assert result["columns"]
    assert all(value is None or -1 <= value <= 1
               for row in result["matrix"] for value in row)


# ------------------------------------------------------------------ نوسان
def test_movers_compare_the_two_halves(frame):
    cleaned = clean(frame, CleanOptions()).frame
    result = movers(cleaned, "مبلغ فروش", "تاریخ", "منطقه")
    assert result["reason"] == ""
    assert result["gainers"] or result["losers"]
    for item in result["gainers"] + result["losers"]:
        assert item["before"] != 0
        assert abs(item["change"]) <= 100


def test_movers_skips_groups_missing_from_a_half():
    """گروهی که در یک نیمه مقدار ندارد از مقایسه کنار می‌رود، نه این‌که
    «رشد بی‌نهایت» بگیرد."""
    rows = []
    for index in range(20):
        rows.append({"تاریخ": f"1403/01/{index + 1:02d}", "گروه": "الف",
                     "مبلغ": 100})
    for index in range(20):
        rows.append({"تاریخ": f"1403/07/{index + 1:02d}", "گروه": "ب",
                     "مبلغ": 200})
    frame = pd.DataFrame(rows)
    result = movers(frame, "مبلغ", "تاریخ", "گروه")
    labels = [item["label"] for item in result["gainers"] + result["losers"]]
    assert "ب" not in labels


def test_movers_needs_the_right_columns(frame):
    cleaned = clean(frame, CleanOptions()).frame
    assert movers(cleaned, "", "تاریخ", "منطقه")["reason"]
    assert movers(cleaned, "مبلغ فروش", "", "منطقه")["reason"]


# ------------------------------------------------------------------ محورها
def test_manual_axis_selection_is_respected(frame):
    cleaned = clean(frame, CleanOptions()).frame
    profile = profile_frame(cleaned)
    analysis = analyse(cleaned, profile, metric="تعداد", dimension="محصول")
    assert analysis.primary_metric == "تعداد"
    assert analysis.primary_dimension == "محصول"


def test_unknown_axis_falls_back_and_says_so(frame):
    cleaned = clean(frame, CleanOptions()).frame
    profile = profile_frame(cleaned)
    analysis = analyse(cleaned, profile, metric="ستون ناموجود")
    assert analysis.primary_metric != "ستون ناموجود"
    assert any("ناموجود" in note for note in analysis.notes)


def test_analysis_is_serialisable(frame):
    _frame, _profile, analysis = _pipeline(frame)
    payload = analysis.as_dict()
    for key in ("kpis", "insights", "series", "breakdowns", "anomalies",
                "correlation", "notes", "primary_metric"):
        assert key in payload
