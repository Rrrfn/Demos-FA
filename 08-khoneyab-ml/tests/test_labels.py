# -*- coding: utf-8 -*-
"""آزمون برچسب‌ها و قالب‌بندی فارسی."""
from __future__ import annotations

import re

from khoneyab.config import to_persian_digits
from khoneyab.labels import (bedrooms_label, district_name, fa_number, fa_percent,
                             fa_price, fa_price_per_m2, fa_price_short,
                             feature_delta_label, feature_value_label, floor_label)

LATIN_DIGITS = re.compile(r"[0-9]")


def test_persian_digits_replacement():
    assert to_persian_digits(1402) == "۱۴۰۲"
    assert LATIN_DIGITS.search(to_persian_digits("منطقه 22")) is None


def test_number_grouping_uses_persian_separator():
    text = fa_number(1234567)
    assert text == "۱٬۲۳۴٬۵۶۷"
    assert "," not in text


def test_number_with_decimals():
    assert fa_number(12.3456, decimals=2) == "۱۲٫۳۵"


def test_price_formatting():
    assert fa_price(2_500_000_000).endswith("تومان")
    assert "۲٫۵۰ میلیارد" == fa_price_short(2_500_000_000)
    assert fa_price_short(750_000_000) == "۷۵۰ میلیون"
    assert fa_price_short(900_000) == "۹۰۰٬۰۰۰"
    assert "تومان/متر" in fa_price_per_m2(95_000_000)


def test_percent_sign_and_direction():
    assert fa_percent(0.123, signed=True).startswith("+")
    assert fa_percent(-0.123, signed=True).startswith("−")
    assert fa_percent(0.5) == "۵۰٫۰٪"


def test_floor_labels():
    assert floor_label(-1) == "زیرزمین"
    assert floor_label(0) == "همکف"
    assert floor_label(3) == "طبقه ۳"


def test_bedroom_labels():
    assert bedrooms_label(0) == "بدون اتاق"
    assert bedrooms_label(3) == "۳ خواب"


def test_district_name_is_persian():
    text = district_name(1)
    assert text.startswith("منطقه ۱")
    assert LATIN_DIGITS.search(text) is None
    assert "—" in text


def test_feature_value_labels():
    assert feature_value_label("parking", 1) == "دارد"
    assert feature_value_label("parking", 0) == "ندارد"
    assert feature_value_label("area", 120) == "۱۲۰ مترمربع"
    assert feature_value_label("age", 5) == "۵ سال"
    assert feature_value_label("bedrooms", 3) == "۳ اتاق"
    assert feature_value_label("floor", 0) == "همکف"
    assert feature_value_label("district", 2).startswith("منطقه ۲")


def test_feature_delta_labels_are_persian():
    assert feature_delta_label("parking", -1_000_000) == "پارکینگ (ندارد)"
    assert feature_delta_label("parking", 1_000_000) == "پارکینگ (دارد)"
    assert feature_delta_label("district", 5) == "جایگاه منطقه"
    assert feature_delta_label("area", 1) == "متراژ"
    for feature in ("district", "area", "bedrooms", "age", "floor", "parking",
                    "storage", "elevator"):
        assert LATIN_DIGITS.search(feature_delta_label(feature, 1)) is None
