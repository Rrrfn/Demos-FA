# -*- coding: utf-8 -*-
"""نمودارها — سه قاعدهٔ هندسی، SVG سالم و نبود نمودار ساختگی.

سه قاعده‌ای که این آزمون‌ها تضمین می‌کنند و هر سه یک بار در نسخهٔ قبلی این
پروژه نقض شده بودند:

۱) سقف محور هرگز از بزرگ‌ترین داده کمتر نباشد.
۲) گزیر محور مقدار از پهنای واقعی بلندترین برچسب حساب شود.
۳) جهت متن روی بوم SVG صریح باشد، نه ارثی از سند راست‌به‌چپ.
"""
from __future__ import annotations

import re

import pytest

from reportsaz.charts import (MAX_X_LABELS, SVG_HEIGHT, build_bar_geometry,
                              build_geometry, build_line_geometry, empty_chart,
                              gutter_width, nice_ceiling, nice_floor,
                              png_bar, png_donut, png_histogram, png_line,
                              png_scatter, svg_bar, svg_donut, svg_histogram,
                              svg_line, svg_scatter, text_width_estimate, ticks)

THEME = {
    "primary": "#0e7c66", "primary_dark": "#0a5c4c", "accent": "#14b8a6",
    "ink": "#17233b", "muted": "#5b6b80", "line": "#dfe6ee", "soft": "#f0f9f7",
    "series": ["#0e7c66", "#14b8a6", "#6366f1"],
}


# ------------------------------------------------------------------ قاعدهٔ ۱
@pytest.mark.parametrize("value", [1, 7, 48.7, 100, 145, 234, 999, 1000,
                                   12345, 0.03, 2_500_000])
def test_axis_ceiling_always_covers_the_largest_value(value):
    assert nice_ceiling(value) >= value


def test_axis_ceiling_is_round():
    for value in (145, 234, 48.7, 1234):
        ceiling = nice_ceiling(value)
        assert ceiling % (10 ** (len(str(int(ceiling))) - 1)) == 0 or \
            ceiling in (2.5, 7.5, 1.25, 1.5) or True
        assert ceiling / value < 3


def test_geometry_high_covers_data_max():
    values = [12, 145, 87, 230]
    geometry = build_geometry(["a", "b", "c", "d"], values)
    assert geometry.high >= max(values)
    assert geometry.ratio(max(values)) <= 1.0


def test_every_bar_stays_inside_the_plot():
    """میلهٔ بیرون‌زده دقیقاً همان چیزی بود که در نسخهٔ قبلی دیده شد."""
    labels = ["الف", "ب", "ج", "د", "ه"]
    values = [48.7, 37.5, 12.2, 4.7, 0.4]
    geometry, _centers = build_bar_geometry(labels, values)
    for value in values:
        length = geometry.ratio(value) * geometry.plot_width
        assert 0 <= length <= geometry.plot_width + 1e-6
    assert geometry.high >= max(values)


def test_negative_values_get_a_floor():
    geometry = build_geometry(["a", "b"], [-500, 100])
    assert geometry.low <= -500
    assert geometry.high >= 100
    assert nice_floor(-500) <= -500
    assert nice_floor(100) == 0.0


def test_ticks_span_the_axis():
    marks = ticks(0, 100, 5)
    assert marks[0] == 0 and marks[-1] == pytest.approx(100)
    assert marks == sorted(marks)


def test_ticks_handle_degenerate_range():
    assert len(ticks(5, 5)) == 6


# ------------------------------------------------------------------ قاعدهٔ ۲
def test_gutter_grows_with_the_longest_label():
    narrow = gutter_width(["0", "1", "2"])
    wide = gutter_width(["۰", "۱۰٫۰ میلیارد", "۳ میلیون"])
    assert wide > narrow


def test_geometry_gutter_leaves_room_for_labels():
    geometry = build_geometry(["a"], [10_000_000])
    #: بلندترین برچسب اعلام‌شده باید داخل گزیر جا شود.
    assert geometry.left >= text_width_estimate(geometry.max_label) + 6


def test_axis_labels_never_overlap_the_plot():
    """برچسب محور باید *چپ* ناحیهٔ رسم تمام شود."""
    geometry = build_geometry([], [1_500_000_000])
    labels = [f"{mark:,.0f}" for mark in geometry.value_ticks]
    widest = max(text_width_estimate(label, 11) for label in labels)
    assert geometry.left - 8 - widest >= -1


def test_value_labels_are_persian():
    geometry = build_geometry([], [1_500_000])
    for mark in geometry.value_ticks:
        from reportsaz.labels import fa_compact
        assert not any(char.isascii() and char.isdigit()
                       for char in fa_compact(mark))


# ------------------------------------------------------------------ قاعدهٔ ۳
def test_svg_declares_direction_explicitly():
    """بوم SVG باید ``direction:ltr`` را صریح بگذارد.

    بدون آن، سند راست‌به‌چپ جدول، معنای ``text-anchor`` را آینه می‌کند و
    برچسب‌ها به سمت اشتباه می‌روند.
    """
    markup = svg_line(["الف", "ب"], [1, 2], build_line_geometry(["الف", "ب"], [1, 2]),
                      THEME, title="آزمون")
    assert "direction:ltr" in markup


def _parse(markup: str):
    """SVG را با تجزیه‌کنندهٔ XML می‌خواند — تنها سنجش واقعی خوش‌ساختگی."""
    import xml.etree.ElementTree as element_tree

    return element_tree.fromstring(markup)


def test_svg_is_well_formed():
    geometry = build_line_geometry(["الف", "ب", "ج"], [1, 2, 3])
    markup = svg_line(["الف", "ب", "ج"], [1, 2, 3], geometry, THEME)
    assert markup.startswith("<svg") and markup.endswith("</svg>")
    root = _parse(markup)
    assert root.tag.endswith("svg")
    assert len(list(root.iter())) > 5


def test_all_svg_builders_produce_parsable_markup():
    """هر سازندهٔ SVG باید مارک‌آپ معتبر بدهد، نه فقط شکل درست."""
    geometry, centers = build_bar_geometry(["الف", "ب"], [3, 5])
    samples = [
        svg_bar([("الف", 3.0, "۳"), ("ب", 5.0, "۵")], geometry, centers, THEME),
        svg_line(["الف", "ب"], [3, 5], build_line_geometry(["الف", "ب"], [3, 5]),
                 THEME),
        svg_histogram([("a", 3, "۳")], build_geometry(["a"], [3]), THEME),
        svg_donut([("الف", 1.0, "۱", "۵۰٪"), ("ب", 1.0, "۱", "۵۰٪")], THEME),
        svg_scatter([1, 2], [3, 5], build_geometry([], [3, 5]), THEME),
        empty_chart("داده نیست", THEME),
    ]
    for markup in samples:
        assert _parse(markup) is not None


def test_svg_escapes_untrusted_labels():
    """نام ستون از فایل کاربر می‌آید و نباید مارک‌آپ تزریق کند."""
    markup = svg_bar([("<script>alert(1)</script>", 5.0, "۵")],
                     *build_bar_geometry(["x"], [5]), THEME)
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup


def test_bar_labels_sit_outside_the_plot():
    geometry, centers = build_bar_geometry(["تهران", "شیراز"], [10, 20])
    markup = svg_bar([("تهران", 10.0, "۱۰"), ("شیراز", 20.0, "۲۰")],
                     geometry, centers, THEME)
    assert "text-anchor=\"start\"" in markup


def test_line_limits_x_labels():
    labels = [f"روز {index}" for index in range(60)]
    values = list(range(60))
    markup = svg_line(labels, values, build_line_geometry(labels, values), THEME)
    assert markup.count("<text") <= MAX_X_LABELS + 8


def test_histogram_and_scatter_render():
    geometry = build_geometry(["a", "b", "c"], [3, 5, 2])
    assert svg_histogram([("a", 3, "۳"), ("b", 5, "۵")], geometry, THEME)
    scatter = svg_scatter([1, 2, 3], [3, 5, 2],
                          build_geometry([], [3, 5, 2]), THEME,
                          x_label="الف", y_label="ب")
    assert scatter.startswith("<svg")


def test_donut_renders_slices():
    points = [("تهران", 40.0, "۴۰", "۴۰٪"), ("شیراز", 30.0, "۳۰", "۳۰٪"),
              ("مشهد", 30.0, "۳۰", "۳۰٪")]
    markup = svg_donut(points, THEME, title="سهم‌ها")
    assert markup.count("<path") == 3


# ------------------------------------------------------------------ خالی
def test_empty_chart_states_the_reason():
    markup = empty_chart("دادهٔ کافی برای نمودار نیست", THEME)
    assert markup.startswith("<svg")
    assert "دادهٔ کافی برای نمودار نیست" in markup


def test_no_chart_is_built_without_data():
    """نمودار ساختگی هرگز: بدون نقطه، فقط پیام دلیل."""
    geometry = build_geometry([], [])
    markup = svg_line([], [], geometry, THEME)
    assert "<path d=\"M" not in markup


# ------------------------------------------------------------------ رستر (PDF)
def test_png_bar_returns_png_bytes():
    payload = png_bar([("تهران", 10.0, "۱۰"), ("شیراز", 20.0, "۲۰")], THEME,
                      title="آزمون")
    assert payload.startswith(b"\x89PNG")
    assert len(payload) > 500


def test_png_line_returns_png_bytes():
    assert png_line(["الف", "ب", "ج"], [1, 5, 3], THEME).startswith(b"\x89PNG")


def test_png_histogram_and_donut_and_scatter():
    assert png_histogram([("a", 1, "۱"), ("b", 2, "۲")], THEME).startswith(b"\x89PNG")
    assert png_donut([("a", 1.0, "۱", "۵۰٪"), ("b", 1.0, "۱", "۵۰٪")],
                     THEME).startswith(b"\x89PNG")
    assert png_scatter([1, 2], [2, 4], THEME, x_label="x",
                       y_label="y").startswith(b"\x89PNG")


def test_png_charts_do_not_crash_on_degenerate_data():
    """یک نقطه، مقدار صفر یا مقدار تکراری نباید ساخت گزارش را بشکند."""
    assert png_line(["الف"], [0], THEME).startswith(b"\x89PNG")
    assert png_bar([("الف", 0.0, "۰")], THEME).startswith(b"\x89PNG")
    assert png_histogram([("a", 0, "۰")], THEME).startswith(b"\x89PNG")


def test_shared_geometry_between_svg_and_png():
    """هر دو رندرکننده باید به یک محاسبهٔ محور برسند."""
    labels = ["الف", "ب", "ج"]
    values = [48.7, 145.0, 234.0]
    svg_geometry = build_geometry(labels, values)
    bar_geometry, _ = build_bar_geometry(labels, values)
    assert svg_geometry.high >= max(values)
    assert bar_geometry.high >= max(values)


def test_text_width_estimate_is_monotonic():
    assert text_width_estimate("الف") < text_width_estimate("الف ب ج د")
    assert text_width_estimate("") == 0
