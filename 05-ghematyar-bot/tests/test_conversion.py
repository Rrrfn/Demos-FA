# -*- coding: utf-8 -*-
"""تست تبدیل واحد و قالب‌بندی ارقام."""
from __future__ import annotations

import pytest

from ghematyar.core.formatting import (
    arrow,
    fa_num,
    fa_pct,
    fa_price,
    fa_signed,
    to_float,
    to_int,
)
from ghematyar.providers.tgju import _clean_number, _parse_change_cell, _to_unit


class TestRialToToman:
    """تبدیل ریال به تومان — خطای ضریب ۱۰ برابر فاجعه‌بار است."""

    def test_rial_is_divided_by_ten(self):
        assert _to_unit(241_814_000, "toman") == 24_181_400

    def test_usd_is_untouched(self):
        assert _to_unit(78_706.33, "usd") == 78_706.33

    def test_zero_stays_zero(self):
        assert _to_unit(0, "toman") == 0


class TestNumberCleaning:
    """پارس مقادیر خوراک."""

    def test_comma_separated(self):
        assert _clean_number("2,359,750") == 2_359_750

    def test_float_string(self):
        assert _clean_number("78706.33") == pytest.approx(78_706.33)

    def test_numeric_input(self):
        assert _clean_number(1234) == 1234

    @pytest.mark.parametrize("value", [None, "", "-", "—", "N/A"])
    def test_missing_values_are_none(self, value):
        """مقدار نامعتبر باید None شود، نه صفر — صفر یک قیمت است."""
        assert _clean_number(value) is None


class TestChangeCell:
    """پارس سلول تغییر صفحهٔ tgju: ``(1.86%) 1436.08``."""

    def test_percent_and_absolute(self):
        pct, absolute = _parse_change_cell("(1.86%) 1436.08")
        assert pct == pytest.approx(1.86)
        assert absolute == pytest.approx(1436.08)

    def test_negative_change(self):
        pct, absolute = _parse_change_cell("(-0.54%) -420.5")
        assert pct == pytest.approx(-0.54)
        assert absolute == pytest.approx(-420.5)

    def test_zero_means_not_reported(self):
        """صفرِ tgju «بدون تغییر» نیست؛ «گزارش‌نشده» است."""
        pct, absolute = _parse_change_cell("(0%) 0")
        assert pct is None
        assert absolute is None

    def test_malformed_cell(self):
        assert _parse_change_cell("چیزی") == (None, None)


class TestTextParsing:
    """تبدیل متن با ارقام فارسی/عربی."""

    def test_persian_digits(self):
        assert to_int("۲۵۰٬۰۰۰") == 250_000

    def test_arabic_digits(self):
        assert to_int("١٢٣٤") == 1234

    def test_float_with_persian_separator(self):
        assert to_float("۲٫۵") == pytest.approx(2.5)

    def test_garbage_returns_zero(self):
        assert to_int("abc") == 0
        assert to_float("abc") == 0.0


class TestDisplayFormatting:
    """قالب‌بندی نمایش."""

    def test_persian_grouping(self):
        assert fa_num(1_234_567) == "۱٬۲۳۴٬۵۶۷"

    def test_price_with_unit(self):
        assert fa_price(250_000, "toman") == "۲۵۰٬۰۰۰ تومان"
        assert fa_price(78_706.33, "usd", 2) == "۷۸٬۷۰۶٫۳۳ دلار"

    def test_signed_value(self):
        assert fa_signed(1500) == "+۱٬۵۰۰"
        assert fa_signed(-1500) == "−۱٬۵۰۰"

    def test_percentage_trims_zeros(self):
        assert fa_pct(2.5) == "۲٫۵٪"
        assert fa_pct(0.5) == "۰٫۵٪"

    def test_arrows(self):
        assert arrow(1) == "▲"
        assert arrow(-1) == "▼"
        assert arrow(0) == "•"
