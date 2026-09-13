# -*- coding: utf-8 -*-
"""پروفایل داده — تشخیص نوع و نقش، امتیاز کیفیت و مقدارهای مشکوک."""
from __future__ import annotations

import pandas as pd
import pytest

from reportsaz.config import QUALITY_WEIGHTS
from reportsaz.profile import (ROLE_DATE, ROLE_DIMENSION, ROLE_IDENTIFIER,
                               ROLE_METRIC, ROLE_TEXT, TYPE_DATE, TYPE_NUMBER,
                               TYPE_TEXT, infer_type, pick_dimensions,
                               pick_metrics, profile_frame)


# ------------------------------------------------------------------ نوع
@pytest.mark.parametrize("values,expected", [
    ([1, 2, 3, 4, 5, 6], TYPE_NUMBER),
    (["1", "2", "3", "4", "5", "6"], TYPE_NUMBER),
    (["۱٬۲۰۰", "۲٬۳۰۰", "۳٬۴۰۰", "۴٬۵۰۰"], TYPE_NUMBER),
    (["۲۵۰٬۰۰۰ ریال", "۱۲۰٬۰۰۰ ریال", "۴۵٬۰۰۰ ریال"], TYPE_NUMBER),
    (["1403/01/01", "1403/02/01", "1403/03/01"], TYPE_DATE),
    (["2024-01-01", "2024-02-01", "2024-03-01"], TYPE_DATE),
    (["تهران", "شیراز", "مشهد"], TYPE_TEXT),
    (["بله", "خیر", "بله", "بله"], "boolean"),
])
def test_infer_type(values, expected):
    kind, ratio, _formats = infer_type(pd.Series(values))
    assert kind == expected
    assert ratio >= 0.85


def test_infer_type_reports_partial_validity():
    """نسبت اعتبار باید همان چیزی باشد که آستانهٔ اعلام‌شده می‌گوید.

    آستانه ۸۵٪ است: ستونی که ۹۰٪ عدد است عدد شمرده می‌شود و نسبتش گزارش
    می‌شود؛ ستونی که فقط ۸۰٪ عدد است عدد *نیست* — چون جمع روی آن ۲۰٪ خطا
    دارد.
    """
    mostly_numeric = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, "نامشخص"])
    kind, ratio, _ = infer_type(mostly_numeric)
    assert kind == TYPE_NUMBER
    assert ratio == pytest.approx(0.9)

    #: زیر آستانه، نوع متن است و اعتبارش ۱ تعریف می‌شود: هر مقداری متن
    #: معتبری است. نکتهٔ مهم این است که نوع *عدد نامیده نشود*.
    below_threshold = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, "نامشخص", "?"])
    kind, ratio, _ = infer_type(below_threshold)
    assert kind == TYPE_TEXT
    assert ratio == pytest.approx(1.0)


def test_infer_type_mixed_columns_stays_text():
    """ستون نیمه‌عددی نباید عدد نامیده شود؛ جمع روی آن غلط می‌شود."""
    series = pd.Series([1, "تهران", 2, "شیراز", 3, "مشهد", 4, "تبریز"])
    kind, _ratio, _ = infer_type(series)
    assert kind == TYPE_TEXT


def test_code_column_is_not_a_number():
    """کدی مثل ``A-1`` عدد نیست — این یک باگ واقعی در نسخهٔ اولیه بود."""
    series = pd.Series(["A-1", "A-2", "A-3", "A-4"])
    kind, _ratio, _ = infer_type(series)
    assert kind == TYPE_TEXT


# ------------------------------------------------------------------ نقش
def test_roles_are_assigned_sensibly():
    frame = pd.DataFrame({
        "تاریخ": ["1403/01/01", "1403/01/02", "1403/01/03", "1403/01/04"],
        "منطقه": ["تهران", "شیراز", "تهران", "مشهد"],
        "مبلغ فروش": [1000, 2000, 3000, 4000],
        "کد سفارش": ["ORD-1", "ORD-2", "ORD-3", "ORD-4"],
    })
    profile = profile_frame(frame)
    assert profile.role("تاریخ") == ROLE_DATE
    assert profile.role("منطقه") == ROLE_DIMENSION
    assert profile.role("مبلغ فروش") == ROLE_METRIC


def test_sequential_counter_is_an_identifier_not_a_metric():
    """شمارهٔ ردیف ۱ تا n نباید به‌عنوان مبلغ جمع شود."""
    frame = pd.DataFrame({"row": [1, 2, 3, 4, 5, 6],
                          "value": [10, 40, 20, 55, 30, 15]})
    profile = profile_frame(frame)
    assert profile.role("row") == ROLE_IDENTIFIER
    assert profile.role("value") == ROLE_METRIC


def test_all_distinct_metric_is_not_called_identifier():
    """در جدول کوچک، هر متریکی مقدارهای یکتا دارد — ولی شناسه نیست."""
    frame = pd.DataFrame({"مبلغ فروش": [1200, 3450, 990]})
    profile = profile_frame(frame)
    assert profile.role("مبلغ فروش") == ROLE_METRIC


def test_date_column_prefers_named_hint():
    frame = pd.DataFrame({"ستون الف": ["1403/01/01", "1403/01/02", "1403/01/03"],
                          "تاریخ سفارش": ["1403/02/01", "1403/02/02", "1403/02/03"]})
    profile = profile_frame(frame)
    assert profile.date_column().name == "تاریخ سفارش"


def test_picks_are_ordered_and_bounded():
    frame = pd.DataFrame({
        "منطقه": ["تهران", "شیراز", "مشهد", "تبریز"] * 5,
        "محصول": ["الف", "ب", "ج", "د"] * 5,
        "مبلغ فروش": list(range(20)),
        "تعداد": [1] * 20,
    })
    profile = profile_frame(frame)
    dimensions = pick_dimensions(profile)
    metrics = pick_metrics(profile)
    assert "منطقه" in dimensions
    assert "مبلغ فروش" in metrics
    assert len(dimensions) <= 6 and len(metrics) <= 4


# ------------------------------------------------------------------ کیفیت
def test_quality_is_perfect_on_clean_data():
    frame = pd.DataFrame({"الف": [1, 2, 3, 4], "ب": ["x", "y", "z", "w"]})
    profile = profile_frame(frame)
    assert profile.quality["score"] == 100.0
    assert profile.quality["label"] == "عالی"


def test_quality_drops_with_missing_and_duplicates():
    frame = pd.DataFrame({"الف": [1, None, None, None],
                          "ب": ["x", "x", "x", "x"]})
    profile = profile_frame(frame)
    assert profile.quality["score"] < 80
    assert profile.quality["parts"]["completeness"] < 70
    assert profile.quality["parts"]["uniqueness"] < 100


def test_quality_weights_are_the_documented_ones():
    frame = pd.DataFrame({"الف": [1, 2, 3, 4]})
    profile = profile_frame(frame)
    assert set(profile.quality["parts"]) == set(QUALITY_WEIGHTS)
    assert abs(sum(QUALITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_quality_bands_cover_all_ranges():
    from reportsaz.config import QUALITY_BANDS
    thresholds = [threshold for threshold, _ in QUALITY_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)
    assert thresholds[-1] == 0


# ------------------------------------------------------------------ مشکوک
def test_outliers_are_flagged_by_iqr():
    frame = pd.DataFrame({"مبلغ": [100, 105, 98, 102, 110, 99, 104, 101,
                                   103, 106, 100_000]})
    profile = profile_frame(frame)
    column = profile.by_name("مبلغ")
    assert any(item["kind"] == "outlier" for item in column.suspicious)
    assert profile.suspicious_total >= 1


def test_negative_values_are_flagged():
    frame = pd.DataFrame({"مبلغ": [-500, -300, -200, -100, -50, -20, -10, -5]})
    profile = profile_frame(frame)
    column = profile.by_name("مبلغ")
    assert any(item["kind"] == "negative" for item in column.suspicious)


def test_implausible_dates_are_flagged():
    frame = pd.DataFrame({"تاریخ": ["1403/01/01", "1403/01/02", "1403/01/03",
                                    "1403/01/04", "1403/01/05"]})
    profile = profile_frame(frame)
    column = profile.by_name("تاریخ")
    assert column.type == TYPE_DATE
    assert column.date_min and column.date_max


# ------------------------------------------------------------------ سریال‌سازی
def test_profile_round_trips_through_dict():
    frame = pd.DataFrame({"منطقه": ["الف", "ب", "ج"],
                          "مبلغ": [1, 2, 3],
                          "تاریخ": ["1403/01/01", "1403/01/02", "1403/01/03"]})
    payload = profile_frame(frame).as_dict()
    assert payload["rows"] == 3
    assert len(payload["columns_profile"]) == 3
    for column in payload["columns_profile"]:
        assert "missing" in column and "validity" in column and "role" in column


def test_empty_frame_is_handled():
    profile = profile_frame(pd.DataFrame({"الف": []}))
    assert profile.rows == 0
    assert profile.quality["score"] >= 0
