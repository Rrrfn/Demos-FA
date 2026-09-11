# -*- coding: utf-8 -*-
"""تست پارسر عبارت‌های هشدار — منطق خالص، بدون شبکه."""
from __future__ import annotations

import pytest

from ghematyar.bot.parsing import detect_direction, parse_alert_expression
from ghematyar.storage import AlertDirection


class TestDirection:
    """تشخیص جهت شرط."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("دلار بالای ۲۵۰۰۰۰", AlertDirection.ABOVE),
            ("دلار بالاتر از ۲۵۰۰۰۰", AlertDirection.ABOVE),
            ("دلار بیشتر از ۲۵۰۰۰۰", AlertDirection.ABOVE),
            ("دلار زیر ۲۵۰۰۰۰", AlertDirection.BELOW),
            ("دلار کمتر از ۲۵۰۰۰۰", AlertDirection.BELOW),
            ("دلار پایین‌تر از ۲۵۰۰۰۰", AlertDirection.BELOW),
        ],
    )
    def test_common_phrasings(self, text, expected):
        assert detect_direction(text) is expected

    def test_no_direction_returns_none(self):
        assert detect_direction("دلار چنده؟") is None


class TestAssetDetection:
    """تشخیص قلم از نام فارسی، کلیدواژه یا لاتین."""

    @pytest.mark.parametrize(
        "text,slug",
        [
            ("دلار بالای ۲۵۰۰۰۰", "usd"),
            ("قیمت یورو بالای ۳۰۰۰۰۰", "eur"),
            ("طلای ۱۸ عیار بالای ۵۰۰۰۰۰۰۰", "geram18"),
            ("طلا بالای ۵۰۰۰۰۰۰۰", "geram18"),
            ("سکه امامی زیر ۲۰۰۰۰۰۰۰۰", "sekee"),
            ("نیم‌سکه بالای ۱۰۰۰۰۰۰۰۰", "nim"),
            ("ربع سکه زیر ۵۰۰۰۰۰۰۰", "rob"),
            ("بیت‌کوین بالای ۸۰۰۰۰", "bitcoin"),
            ("BTC بالای ۸۰۰۰۰", "bitcoin"),
            ("اتریوم زیر ۲۰۰۰", "ethereum"),
            ("مثقال بالای ۱۰۰۰۰۰۰۰۰", "mesghal"),
        ],
    )
    def test_asset_from_expression(self, text, slug):
        assert parse_alert_expression(text).slug == slug

    def test_nim_does_not_collide_with_coin(self):
        """«نیم‌سکه» نباید به «سکه» تفسیر شود."""
        assert parse_alert_expression("نیم‌سکه بالای ۵۰۰۰۰۰۰۰").slug == "nim"

    def test_unknown_asset(self):
        assert parse_alert_expression("آبمیوه بالای ۵۰۰۰۰").slug is None


class TestTarget:
    """استخراج آستانه، از جمله ضریب‌های کلامی."""

    def test_plain_number(self):
        expression = parse_alert_expression("دلار بالای ۲۵۰۰۰۰")
        assert expression.target == 250_000

    def test_thousand_separators(self):
        expression = parse_alert_expression("دلار بالای 2,500,000")
        assert expression.target == 2_500_000

    def test_billion_scale(self):
        expression = parse_alert_expression("سکه امامی زیر ۲ میلیارد")
        assert expression.target == 2_000_000_000

    def test_million_scale(self):
        expression = parse_alert_expression("طلای ۱۸ بالای ۵ میلیون")
        assert expression.target == 5_000_000

    def test_decimal_milliard(self):
        """«۲.۵ میلیارد» باید درست تفسیر شود."""
        expression = parse_alert_expression("سکه زیر ۲.۵ میلیارد")
        assert expression.target == 2_500_000_000

    def test_missing_number(self):
        expression = parse_alert_expression("دلار بالای")
        assert expression.target is None
        assert expression.direction is AlertDirection.ABOVE


class TestCompleteness:
    """تشخیص کامل بودن یا ناقص بودن عبارت."""

    def test_complete_expression(self):
        expression = parse_alert_expression("بیت‌کوین بالای ۸۵۰۰۰ دلار")
        assert expression.complete is True
        assert expression.slug == "bitcoin"
        assert expression.direction is AlertDirection.ABOVE
        assert expression.target == 85_000

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "سلام", "دلار بالای", "بالای ۲۵۰۰۰۰", "دلار ۲۵۰۰۰۰"],
    )
    def test_incomplete_expressions(self, text):
        assert parse_alert_expression(text).complete is False

    def test_empty_input_is_safe(self):
        expression = parse_alert_expression("")
        assert expression.slug is None
        assert expression.direction is None
        assert expression.target is None
