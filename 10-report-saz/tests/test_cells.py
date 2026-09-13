# -*- coding: utf-8 -*-
"""تجزیهٔ مقدار سلول — عدد، تاریخ و بولی از متن فارسی و لاتین."""
from __future__ import annotations

import datetime as dt

import pytest

from reportsaz.ingest.cells import (clean_text, jalali_to_gregorian,
                                    normalize_digits, parse_bool, parse_date,
                                    parse_number, plausible_date)


# ------------------------------------------------------------------ ارقام
@pytest.mark.parametrize("raw,expected", [
    ("۱۲۳", "123"),
    ("٣٤٥", "345"),
    ("۳٫۵", "3.5"),
    ("۱٬۲۰۰٬۰۰۰", "1,200,000"),
])
def test_normalize_digits(raw, expected):
    assert normalize_digits(raw) == expected


def test_normalize_digits_keeps_decimal_separator():
    """ممیز فارسی باید به نقطه تبدیل شود، نه حذف.

    اگر حذف شود، «۳٫۵» به «۳۵» تبدیل می‌شود — عددی ده برابر مقدار واقعی.
    """
    assert parse_number("۳٫۵") == pytest.approx(3.5)
    assert parse_number("۱۲٫۷۵") == pytest.approx(12.75)


# ------------------------------------------------------------------ عدد
@pytest.mark.parametrize("raw,expected", [
    (1200, 1200.0),
    ("1,200,000", 1_200_000.0),
    ("۱٬۲۰۰٬۰۰۰", 1_200_000.0),
    ("۲۵۰٬۰۰۰ ریال", 250_000.0),
    ("25,000 تومان", 25_000.0),
    ("(۳٬۲۰۰)", -3_200.0),
    ("-4500", -4500.0),
    ("−۴۵۰۰", -4500.0),
    ("4500-", -4500.0),
    ("$12,500", 12_500.0),
    ("۳٫۵٪", 3.5),
    ("۲۵۰ هزار", 250_000.0),
    ("۱٫۵ میلیون", 1_500_000.0),
    ("۵ میلیارد", 5e9),
    ("10 عدد", 10.0),
    ("  42  ", 42.0),
    ("1.234,56", 1234.56),
    (0, 0.0),
])
def test_parse_number_accepted(raw, expected):
    assert parse_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [
    None, "", "  ", "-", "—", "n/a", "N/A", "null", "بدون مقدار", "نامشخص",
    "?", "؟", "A-1", "SO-10042", "تهران", "الف", "abc", True, False,
    float("nan"), float("inf"),
])
def test_parse_number_rejected(raw):
    """هر چیزی که عدد نیست باید ``None`` بدهد، نه عدد ساختگی.

    مهم‌ترین موردش کدها هستند: ``A-1`` پیش‌تر منفی یک خوانده می‌شد و
    میانگین ستون شناسه را بی‌صدا خراب می‌کرد.
    """
    assert parse_number(raw) is None


def test_parse_number_does_not_invent_value_from_code():
    assert parse_number("ORD-140100") is None
    assert parse_number("۱۲۳-الف") is None


# ------------------------------------------------------------------ بولی
@pytest.mark.parametrize("raw,expected", [
    (True, True), (False, False),
    ("بله", True), ("آری", True), ("درست", True), ("has", None),
    ("خیر", False), ("نه", False), ("no", False), ("NO", False),
    ("yes", True), ("", None), (None, None), ("شاید", None),
])
def test_parse_bool(raw, expected):
    assert parse_bool(raw) == expected


# ------------------------------------------------------------------ متن
@pytest.mark.parametrize("raw,expected", [
    ("  سلام  ", "سلام"),
    ("الف\u200cب", "الف\u200cب"),
    ("الف\u200fب", "الفب"),
    ("الف   ب", "الف ب"),
    ("الف\u00a0ب", "الف ب"),
    (None, ""),
    ("", ""),
])
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected


# ------------------------------------------------------------------ تقویم
@pytest.mark.parametrize("jalali,gregorian", [
    ((1403, 1, 1), (2024, 3, 20)),
    ((1403, 7, 1), (2024, 9, 22)),
    ((1402, 12, 29), (2024, 3, 19)),
    ((1399, 12, 30), (2021, 3, 20)),
    ((1404, 6, 31), (2025, 9, 22)),
    ((1350, 1, 1), (1971, 3, 21)),
])
def test_jalali_conversion(jalali, gregorian):
    assert jalali_to_gregorian(*jalali) == gregorian


@pytest.mark.parametrize("jalali", [
    (1403, 13, 1),      #: ماه بیرون از بازه
    (1403, 0, 1),
    (1403, 1, 32),      #: فروردین ۳۱ روز دارد
    (1403, 7, 31),      #: مهر ۳۰ روز دارد
    (1403, 1, 0),
])
def test_jalali_rejects_impossible_dates(jalali):
    assert jalali_to_gregorian(*jalali) is None


@pytest.mark.parametrize("raw,expected", [
    ("1403/05/12", dt.date(2024, 8, 2)),
    ("1403-05-12", dt.date(2024, 8, 2)),
    ("۱۲/۰۵/۱۴۰۳", dt.date(2024, 8, 2)),
    ("2024-03-21", dt.date(2024, 3, 21)),
    ("2024/03/21", dt.date(2024, 3, 21)),
    ("21/03/2024", dt.date(2024, 3, 21)),
    ("5 مهر 1403", dt.date(2024, 9, 26)),
    ("2024-03-21 10:30:00", dt.date(2024, 3, 21)),
    ("2024-03-21T10:30:00", dt.date(2024, 3, 21)),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_accepts_date_objects():
    assert parse_date(dt.date(2024, 5, 1)) == dt.date(2024, 5, 1)
    assert parse_date(dt.datetime(2024, 5, 1, 8, 0)) == dt.date(2024, 5, 1)


@pytest.mark.parametrize("raw", [
    None, "", "n/a", "چهارده", "1403", "12", "abc", "؟",
])
def test_parse_date_rejected(raw):
    assert parse_date(raw) is None


def test_parse_date_named_month_was_broken():
    """پیش‌تر ``split(' ')[0]`` فهرست ماه‌های نام‌دار را از بین می‌برد."""
    assert parse_date("۵ مهر ۱۴۰۳") is not None
    assert parse_date("1 January 2024") == dt.date(2024, 1, 1)


def test_plausible_date_window():
    assert plausible_date(dt.date(2024, 1, 1))
    assert not plausible_date(dt.date(1899, 1, 1))
    assert not plausible_date(dt.date(2200, 1, 1))
    assert not plausible_date(None)
