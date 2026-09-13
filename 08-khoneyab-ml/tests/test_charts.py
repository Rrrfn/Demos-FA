# -*- coding: utf-8 -*-
"""آزمون نمودارها — SVG درست، فارسی، و بی‌داده نازا.

نمودار جای خوبی برای پنهان‌شدن خطاست: صفحه می‌آید، محور بی‌برچسب می‌ماند، و
هیچ‌کس نمی‌فهمد. اینجا خروجی ساختاری بررسی می‌شود: تعداد میله‌ها با تعداد
نقاط بخواند، جهت راست‌به‌چپ رعایت شود، و نمودار از دادهٔ خالی ساخته نشود.
"""
from __future__ import annotations

import re

import pytest

from khoneyab import charts


def _rects(svg: str) -> list[str]:
    return re.findall(r"<rect\b[^>]*>", svg)


def _x(rect: str) -> float:
    return float(re.search(r'x="([\d.]+)"', rect).group(1))


def test_horizontal_bars_draws_one_rect_per_bar():
    svg = charts.horizontal_bars([
        charts.Bar(label="منطقه ۱", value=100),
        charts.Bar(label="منطقه ۲", value=50),
        charts.Bar(label="منطقه ۳", value=25),
    ])
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    # rect برای خطوط راهنما هم کشیده می‌شود؛ پس حداقل به اندازهٔ میله‌ها
    assert len(_rects(svg)) >= 3


def test_horizontal_bars_grow_from_the_right():
    """نمودار افقی در رابط فارسی باید از راست شروع شود."""
    bars = [charts.Bar(label="الف", value=10), charts.Bar(label="ب", value=100)]
    svg = charts.horizontal_bars(bars, width=400, label_width=100)
    rects = _rects(svg)
    # میلهٔ بزرگ‌تر (۱۰۰) باید x کوچک‌تری داشته باشد، چون بلندتر به چپ می‌رود.
    assert min(_x(r) for r in rects) < max(_x(r) for r in rects)


def test_columns_place_the_first_category_on_the_right():
    svg = charts.columns([charts.Bar(label="اول", value=10),
                          charts.Bar(label="دوم", value=30)], width=400)
    assert "اول" in svg and "دوم" in svg
    assert svg.index("اول") < svg.index("دوم")


def test_empty_input_produces_nothing():
    """نمودار بی‌داده نباید یک محور خالی تحویل بدهد."""
    assert charts.horizontal_bars([]) == ""
    assert charts.columns([]) == ""
    assert charts.histogram([]) == ""
    assert charts.grouped_bars([], []) == ""


def test_zero_values_do_not_divide_by_zero():
    svg = charts.horizontal_bars([charts.Bar(label="صفر", value=0),
                                  charts.Bar(label="صفر", value=0)])
    assert svg.startswith("<svg")


def test_histogram_draws_a_rect_per_bucket():
    points = [(index * 10.0, index) for index in range(1, 8)]
    svg = charts.histogram(points)
    assert len(_rects(svg)) >= len(points)


def test_grouped_bars_draws_a_rect_per_value():
    svg = charts.grouped_bars(
        ["KH-۱۰۰۱", "KH-۱۰۰۲"],
        [("قیمت آگهی", [10.0, 20.0], "var(--chart-soft)"),
         ("ارزش برآوردی", [11.0, 19.0], "var(--chart-1)")],
    )
    assert len(_rects(svg)) >= 4


def test_labels_use_persian_digits():
    svg = charts.horizontal_bars(
        [charts.Bar(label="منطقه ۱", value=1234, display="۱٬۲۳۴")],
        unit=" م",
    )
    assert "۱٬۲۳۴" in svg
    assert not re.search(r">[^<]*[0-9]", svg), "رقم لاتین در متن نمودار"


def test_value_is_marked_up_and_escaped():
    svg = charts.horizontal_bars([charts.Bar(label="a & b", value=5,
                                             hint="<script>")])
    assert "&amp;" in svg
    assert "<script>" not in svg


def test_chart_is_accessible_when_it_has_a_title():
    svg = charts.columns([charts.Bar(label="الف", value=1)], title="میانهٔ قیمت")
    assert 'role="img"' in svg
    assert "<title>" in svg


def test_stacked_share_splits_the_full_width():
    svg = charts.stacked_share([("الف", 75.0, "var(--chart-1)"),
                               ("ب", 25.0, "var(--chart-soft)")])
    widths = [float(re.search(r'width="([\d.]+)"', r).group(1)) for r in _rects(svg)]
    assert sum(widths) == pytest.approx(640, abs=1.0)


def test_legend_lists_its_items():
    svg = charts.legend([("قیمت آگهی", "red"), ("ارزش برآوردی", "blue")])
    assert "قیمت آگهی" in svg and "ارزش برآوردی" in svg


@pytest.fixture()
def rendered_pages(client):
    """هرس‌کردن نمودارهای صفحه‌ها برای آزمون یکدستی."""
    return {
        path: set(re.findall(r"<svg class=\"chart\".*?</svg>",
                             client.get(path).get_data(as_text=True), re.S))
        for path in ("/", "/analytics", "/methodology")
    }


def test_pages_render_real_charts(rendered_pages):
    for path, svgs in rendered_pages.items():
        assert svgs, f"{path}: هیچ نموداری رندر نشد"


def test_rendered_charts_have_no_latin_digits(rendered_pages):
    for path, svgs in rendered_pages.items():
        for svg in svgs:
            text = " ".join(re.findall(r">([^<]+)<", svg))
            assert not re.search(r"[0-9]", text), f"{path}: رقم لاتین در نمودار"
