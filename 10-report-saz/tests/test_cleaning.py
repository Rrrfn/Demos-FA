# -*- coding: utf-8 -*-
"""پاک‌سازی — مسائل، اصلاحات، اختیاری بودن و نبود حذف پنهان."""
from __future__ import annotations

import pandas as pd
import pytest

from reportsaz.cleaning import (DEFAULT_ON, OPT_DROP_DUPLICATES,
                                OPT_DROP_EMPTY_COLUMNS, OPT_DROP_EMPTY_ROWS,
                                OPT_NORMALIZE_NULLS, OPT_NUMERIC_AS_TEXT,
                                OPT_PARSE_DATES, OPT_TRIM_TEXT, CleanOptions,
                                clean, detect, options_meta)


def _frame_with_issues() -> pd.DataFrame:
    return pd.DataFrame({
        "منطقه": ["تهران", "تهران", "شیراز", "مشهد"],
        "مبلغ": ["1,200,000", "1,200,000", "۲۵۰٬۰۰۰ ریال", "900"],
        "تاریخ": ["1403/01/05", "1403/01/05", "1403/01/06", "1403/01/07"],
        "پارکینگ": ["دارد", "دارد", " ", "ندارد"],
    })


# ------------------------------------------------------------------ گزینه‌ها
def test_options_cover_all_flag_keys():
    keys = {item["key"] for item in options_meta()}
    assert keys == {OPT_DROP_EMPTY_ROWS, OPT_DROP_DUPLICATES,
                    OPT_DROP_EMPTY_COLUMNS, OPT_TRIM_TEXT,
                    OPT_NUMERIC_AS_TEXT, OPT_PARSE_DATES, OPT_NORMALIZE_NULLS}


def test_default_options_are_all_on():
    assert all(DEFAULT_ON.values())
    assert not CleanOptions.all_off().enabled(OPT_DROP_DUPLICATES)


def test_missing_payload_key_means_on_and_false_means_off():
    """قرارداد: کلید غایب = پیش‌فرض روشن، کلید ``False`` = کاربر خاموشش کرد."""
    options = CleanOptions.from_payload({OPT_DROP_DUPLICATES: False})
    assert options.enabled(OPT_DROP_DUPLICATES) is False
    assert options.enabled(OPT_TRIM_TEXT) is True


# ------------------------------------------------------------------ تشخیص
def test_detect_finds_duplicates_without_changing_data():
    frame = _frame_with_issues()
    before = frame.copy()
    findings = detect(frame)
    keys = {item.key for item in findings}
    assert OPT_DROP_DUPLICATES in keys
    assert OPT_NUMERIC_AS_TEXT in keys
    assert OPT_PARSE_DATES in keys
    pd.testing.assert_frame_equal(frame, before)


def test_detect_reports_exact_counts():
    frame = pd.DataFrame({"a": [1, 1, 1, 1, 2], "b": ["x", "x", "x", "x", "y"]})
    findings = {item.key: item for item in detect(frame)}
    assert findings[OPT_DROP_DUPLICATES].affected == 3


def test_detect_reports_clean_data_as_clean():
    frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    findings = detect(frame)
    assert findings[0].key == "none"
    assert findings[0].affected == 0


# ------------------------------------------------------------------ اعمال
def test_cleaning_removes_duplicates_and_records_it():
    result = clean(_frame_with_issues(), CleanOptions())
    keys = {fix.key for fix in result.fixes}
    assert OPT_DROP_DUPLICATES in keys
    duplicate_fix = next(f for f in result.fixes if f.key == OPT_DROP_DUPLICATES)
    assert duplicate_fix.affected == 1
    assert duplicate_fix.destructive is True
    assert result.rows_before == 4 and result.rows_after == 3


def test_cleaning_converts_numeric_text():
    result = clean(_frame_with_issues(), CleanOptions())
    assert pd.api.types.is_numeric_dtype(result.frame["مبلغ"])
    assert result.frame["مبلغ"].iloc[0] == pytest.approx(1_200_000)
    assert result.frame["مبلغ"].iloc[1] == pytest.approx(250_000)


def test_cleaning_converts_dates():
    """۱ فروردین ۱۴۰۳ برابر ۲۰ مارس ۲۰۲۴ است، پس ۵ فروردین ۲۴ مارس می‌شود."""
    result = clean(_frame_with_issues(), CleanOptions())
    assert pd.api.types.is_datetime64_any_dtype(result.frame["تاریخ"])
    assert str(result.frame["تاریخ"].iloc[0].date()) == "2024-03-24"


def test_cleaning_normalises_hidden_blanks():
    result = clean(_frame_with_issues(), CleanOptions())
    assert int(result.frame["پارکینگ"].isna().sum()) == 1


def test_disabled_options_leave_data_alone():
    """گزینهٔ خاموش نباید هیچ اثری بگذارد."""
    frame = _frame_with_issues()
    result = clean(frame, CleanOptions.all_off())
    assert result.fixes == []
    assert result.rows_after == result.rows_before
    assert result.frame["مبلغ"].dtype == object
    assert result.frame["تاریخ"].dtype == object


def test_single_option_can_be_turned_off():
    options = CleanOptions.from_payload({OPT_DROP_DUPLICATES: False})
    result = clean(_frame_with_issues(), options)
    assert result.rows_after == 4
    assert OPT_DROP_DUPLICATES not in {fix.key for fix in result.fixes}


def test_empty_columns_are_dropped_only_when_allowed():
    frame = pd.DataFrame({"a": [1, 2], "empty": [None, None], "b": ["x", "y"]})
    result = clean(frame, CleanOptions())
    assert "empty" not in result.frame.columns
    keep = clean(frame, CleanOptions.all_off())
    assert "empty" in keep.frame.columns


def test_non_empty_columns_are_never_dropped():
    """حذف ستون فقط برای ستون کاملاً خالی مجاز است."""
    frame = pd.DataFrame({"a": [1, None], "b": ["x", None]})
    result = clean(frame, CleanOptions())
    assert set(result.frame.columns) == {"a", "b"}


def test_cleaning_is_idempotent():
    """اجرای دوبارهٔ پاک‌سازی نباید داده را بیشتر عوض کند."""
    once = clean(_frame_with_issues(), CleanOptions())
    twice = clean(once.frame, CleanOptions())
    assert twice.rows_after == once.rows_after
    pd.testing.assert_frame_equal(once.frame, twice.frame)


def test_outliers_are_never_removed():
    frame = pd.DataFrame({"مبلغ": [100, 101, 102, 103, 104, 105, 106, 99_999]})
    result = clean(frame, CleanOptions())
    assert 99_999 in set(result.frame["مبلغ"])


def test_partial_numeric_column_is_not_coerced():
    """تبدیل ستونی که فقط بخشی از مقدارهایش عدد است، داده را از بین می‌برد."""
    frame = pd.DataFrame({"کد": ["1", "2", "نامشخص", "3", "4"]})
    result = clean(frame, CleanOptions())
    assert result.frame["کد"].dtype == object


def test_result_is_serialisable():
    payload = clean(_frame_with_issues(), CleanOptions()).as_dict()
    for key in ("findings", "fixes", "rows_before", "rows_after", "rows_removed",
                "columns_before", "columns_after"):
        assert key in payload
    assert all({"key", "title", "detail", "affected"} <= set(item)
               for item in payload["fixes"])


def test_every_fix_has_a_human_readable_detail():
    """هر اصلاح باید هم شمار داشته باشد و هم شرح — کاربر باید بفهمد چه شد."""
    result = clean(_frame_with_issues(), CleanOptions())
    for fix in result.fixes:
        assert fix.title.strip()
        assert fix.detail.strip()
        assert fix.affected > 0
