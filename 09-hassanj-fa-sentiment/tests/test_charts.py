# -*- coding: utf-8 -*-
"""آزمون موتور نمودار — سه قاعده‌ای که از باگ‌های واقعی بیرون آمده‌اند.

۱) سقف محور هرگز زیر بزرگ‌ترین مقدار داده نمی‌افتد.
۲) لنگر متن آگاه به جهت است؛ بوم SVG داخل سند راست‌به‌چپ معنای ``text-anchor``
   را آینه می‌کند.
۳) حاشیهٔ محور از پهنای واقعی برچسب حساب می‌شود.

هیچ آزمونی اینجا «شکل» را نمی‌سنجد؛ فقط این‌که هیچ شکلی از قاب بیرون نزند و
هیچ برچسبی بی‌جا نایستد.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from hassanj.charts import (ANCHOR_CENTER, ANCHOR_LEFT, ANCHOR_RIGHT, Bar, columns,
                            grouped_bars, histogram, horizontal_bars, legend,
                            stacked_share)

VIEWBOX = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')


def parse(svg: str) -> tuple[float, float, ET.Element]:
    match = VIEWBOX.search(svg)
    assert match, "viewBox پیدا نشد"
    return float(match.group(1)), float(match.group(2)), ET.fromstring(svg)


def rect_problems(svg: str) -> list[tuple]:
    """مستطیل‌هایی که از قاب بیرون زده‌اند."""
    width, height, root = parse(svg)
    problems = []
    for rect in root.iter("rect"):
        x = float(rect.get("x", 0))
        y = float(rect.get("y", 0))
        w = float(rect.get("width", 0))
        h = float(rect.get("height", 0))
        if x < -0.5 or y < -0.5 or x + w > width + 0.5 or y + h > height + 0.5:
            problems.append((x, y, w, h))
    return problems


def anchors(svg: str) -> set[str]:
    return set(re.findall(r'text-anchor="([^"]+)"', svg))


# ------------------------------------------------------------------ قاعدهٔ اول
def test_horizontal_bars_never_overflow_their_frame():
    for value in (0.4, 1.0, 9.7, 100.0, 1234.5):
        svg = horizontal_bars([Bar(label="الف", value=value, display="")],
                              title="آزمون")
        assert rect_problems(svg) == [], value
        assert anchors(svg) <= {ANCHOR_LEFT, ANCHOR_RIGHT, ANCHOR_CENTER}


def test_columns_never_overflow_their_frame():
    bars = [Bar(label=name, value=value) for name, value in
            (("الف", 0.0), ("ب", 3.3), ("ج", 47.9), ("د", 1234.5))]
    assert rect_problems(columns(bars, title="آزمون")) == []


def test_grouped_bars_never_overflow_their_frame():
    svg = grouped_bars(["الف", "ب"],
                       [("یک", [0.0, 99.9], "var(--chart-1)"),
                        ("دو", [12.3, 0.4], "var(--chart-2)")],
                       unit="٪", title="آزمون")
    assert rect_problems(svg) == []


def test_histogram_never_overflows_its_frame():
    svg = histogram([(5.0, 0), (15.0, 240), (95.0, 12)], unit="٪",
                    x_decimals=0, label_every=1, title="آزمون")
    assert rect_problems(svg) == []


def test_stacked_share_never_overflows_its_frame():
    svg = stacked_share([("الف", 12.0, "var(--chart-1)"),
                         ("ب", 0.0, "var(--chart-2)"),
                         ("ج", 88.0, "var(--chart-3)")], title="آزمون")
    assert rect_problems(svg) == []


def test_all_zero_values_do_not_break_geometry():
    bars = [Bar(label="الف", value=0.0), Bar(label="ب", value=0.0)]
    for svg in (horizontal_bars(bars), columns(bars), stacked_share([])):
        assert rect_problems(svg) == []


# ------------------------------------------------------------------ قاعدهٔ دوم
def test_rtl_canvas_declares_direction_explicitly():
    svg = horizontal_bars([Bar(label="الف", value=1.0)])
    assert 'direction="rtl"' in svg


def test_anchors_are_direction_aware_constants():
    """لنگرها باید از ثابت‌های نام‌دار بیایند، نه رشتهٔ خام.

    در سند راست‌به‌چپ ``start`` لبهٔ راست متن است؛ نوشتن ``end`` جای متن را
    آینه می‌کند و برچسب را از قاب بیرون می‌اندازد.
    """
    assert ANCHOR_RIGHT == "start"
    assert ANCHOR_LEFT == "end"
    assert ANCHOR_CENTER == "middle"

    svg = horizontal_bars([Bar(label="منطقه یک", value=5.0)], show_values=True)
    assert 'text-anchor="start"' in svg


def test_value_labels_are_anchored_to_the_right_of_the_bar():
    svg = horizontal_bars([Bar(label="الف", value=5.0, display="۵")], show_values=True)
    #: عدد سر میله با لنگر راست می‌آید و برچسب ردیف هم راست‌چین است.
    assert svg.count('text-anchor="start"') >= 2


# ------------------------------------------------------------------ قاعدهٔ سوم
def test_value_gutter_grows_with_label_width():
    from hassanj.charts import _value_gutter

    narrow = _value_gutter(["۵"])
    wide = _value_gutter(["۱۲۳٬۴۵۶٫۷ میلیارد"])
    assert narrow < wide
    assert narrow >= 46                      # کف حاشیه
    assert wide <= 150                       # سقف حاشیه


def test_wide_labels_never_reach_into_the_plot():
    """با برچسب بلند، ناحیهٔ رسم باید جمع شود نه این‌که متن داخلش برود."""
    svg = horizontal_bars(
        [Bar(label="منطقه", value=1234.5, display="۱٬۲۳۴٫۵ میلیارد")],
        title="آزمون")
    assert rect_problems(svg) == []
    width, _, root = parse(svg)
    for text in root.iter("text"):
        x = float(text.get("x", 0))
        assert x <= width


# ------------------------------------------------------------------ قیمت‌گذاری اعداد
def test_ticks_always_cover_the_largest_value():
    from hassanj.charts import _ticks

    for top in (0.4, 1.0, 9.7, 47.9, 234.5, 1234.5):
        ticks = _ticks(top)
        assert max(ticks) >= top, top
        assert ticks == sorted(ticks)
        assert ticks[0] == 0.0


def test_ticks_do_not_over_pad():
    """سقف محور نباید بی‌دلیل باز بماند؛ بیش از ۲٫۵ برابر داده پذیرفته نیست."""
    from hassanj.charts import _ticks

    for top in (1.0, 9.7, 47.9, 234.5):
        assert max(_ticks(top)) <= top * 2.5, top


# ------------------------------------------------------------------ دسترس‌پذیری
def test_chart_has_accessible_name_from_title():
    svg = horizontal_bars([Bar(label="الف", value=1.0)], title="عنوان آزمون")
    assert 'role="img"' in svg
    assert 'aria-label="عنوان آزمون"' in svg
    assert "<title>عنوان آزمون</title>" in svg


def test_chart_without_title_is_presentational():
    svg = horizontal_bars([Bar(label="الف", value=1.0)])
    assert 'role="presentation"' in svg and 'aria-hidden="true"' in svg


def test_legend_labels_are_escaped():
    markup = legend([("مثبت & منفی", "var(--label-pos)")])
    assert "&amp;" in markup and "<span" in markup


def test_markup_is_escaped_in_labels_and_titles():
    svg = horizontal_bars([Bar(label="<script>x</script>", value=1.0)],
                          title="<b>بد</b>")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_every_chart_type_shares_one_frame_contract():
    """همهٔ سازنده‌ها باید همان قواعد را رعایت کنند، نه فقط میله‌های افقی."""
    cases = [
        horizontal_bars([Bar(label="الف", value=3.0)]),
        columns([Bar(label="الف", value=3.0)]),
        grouped_bars(["الف"], [("یک", [3.0], "var(--chart-1)")]),
        histogram([(5.0, 3), (55.0, 12)], label_every=1),
        stacked_share([("الف", 3.0, "var(--chart-1)")]),
    ]
    for svg in cases:
        assert rect_problems(svg) == []
        assert 'class="chart"' in svg
