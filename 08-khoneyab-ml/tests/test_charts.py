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


# ------------------------------------------------------------ هندسهٔ نمودار
def _viewbox(svg: str) -> tuple[float, float]:
    parts = re.search(r'viewBox="([^"]+)"', svg).group(1).split()
    return float(parts[2]), float(parts[3])


def _escaping_rects(svg: str, tolerance: float = 0.5) -> list[str]:
    """میله‌هایی که از قاب نمودار بیرون زده‌اند."""
    width, height = _viewbox(svg)
    escaped = []
    for rect in _rects(svg):
        x, y, w, h = (float(re.search(rf'{name}="(-?[\d.]+)"', rect).group(1))
                      for name in ("x", "y", "width", "height"))
        if (x < -tolerance or y < -tolerance
                or x + w > width + tolerance or y + h > height + tolerance):
            escaped.append(rect)
    return escaped


@pytest.mark.parametrize("top", [0.4, 1.0, 7.3, 48.7, 90.0, 121.0, 234.0, 999.0, 1234.5])
def test_axis_never_falls_below_the_largest_value(top):
    """خط آخر محور باید از بزرگ‌ترین مقدار داده کوچک‌تر نباشد.

    اگر کوچک‌تر باشد، بلندی میله از بلندی محور بیشتر می‌شود و میله با ``x``
    یا ``y`` منفی از قاب بیرون می‌زند. این دقیقاً همان شکستی بود که در نمودار
    اهمیت ویژگی و سطل‌های متراژ دیده می‌شد.
    """
    assert max(charts._ticks(top)) >= top


@pytest.mark.parametrize("top", [0.4, 7.3, 48.7, 90.0, 121.0, 234.0, 999.0])
def test_bars_stay_inside_the_canvas(top):
    """هیچ میله‌ای نباید از viewBox بیرون بزند — نه افقی، نه ستونی."""
    bars = [charts.Bar(label=f"گ{index}", value=top * share)
            for index, share in enumerate((1.0, 0.6, 0.05, 0.001))]
    assert _escaping_rects(charts.horizontal_bars(bars)) == []
    assert _escaping_rects(charts.columns(bars)) == []
    assert _escaping_rects(charts.grouped_bars(
        ["الف", "ب"],
        [("یک", [top, top * 0.4], "var(--chart-soft)"),
         ("دو", [top * 0.9, top], "var(--chart-1)")],
    )) == []


def test_rendered_page_charts_stay_inside_their_canvas(rendered_pages):
    """همین قاعده روی نمودارهای واقعیِ صفحه‌ها هم باید برقرار باشد."""
    for path, svgs in rendered_pages.items():
        for svg in svgs:
            assert _escaping_rects(svg) == [], f"{path}: میله از قاب بیرون زده"


def test_horizontal_bars_write_the_value_outside_the_bar():
    """عدد هر میله بیرون سر آن می‌نشیند، نه روی رنگ تیرهٔ میله."""
    svg = charts.horizontal_bars([charts.Bar(label="الف", value=100,
                                             display="۱۰۰")], width=400,
                                 label_width=100)
    bar = next(r for r in _rects(svg) if 'height="20"' in r)
    x = _x(bar)
    value = re.search(r'<text x="([\d.]+)"[^>]*class="chart-value"', svg)
    assert value is not None, "عدد روی میله نوشته نشده"
    assert float(value.group(1)) <= x, "عدد روی میله افتاده است"


def test_columns_write_the_value_above_the_bar():
    svg = charts.columns([charts.Bar(label="الف", value=100, display="۱۰۰")])
    assert 'class="chart-value">۱۰۰' in svg


# ---------------------------------------------------- حاشیهٔ محور عمودی
def _lines(svg: str) -> list[tuple[float, float]]:
    """(کمینهٔ x، کمینهٔ y) هر خط راهنما."""
    out = []
    for line in re.findall(r"<line\b[^>]*>", svg):
        x1 = float(re.search(r'x1="(-?[\d.]+)"', line).group(1))
        x2 = float(re.search(r'x2="(-?[\d.]+)"', line).group(1))
        out.append((min(x1, x2), x1))
    return out


def _plot_left(svg: str) -> float:
    """نخستین x ناحیهٔ رسم — همان جایی که خطوط راهنما شروع می‌شوند."""
    return min(left for left, _ in _lines(svg))


def _value_axis_labels(svg: str) -> list[tuple[float, str]]:
    """برچسب‌های محور مقدار که سمت چپ می‌نشینند، با x لنگرشان.

    جداسازی از روی لنگر انجام می‌شود، نه از روی y: برچسب‌های محور افقی هم
    همان کلاس را دارند ولی وسط‌چین‌اند.
    """
    pattern = (r'<text x="(-?[\d.]+)" y="[\d.]+" '
               r'text-anchor="([a-z]+)" class="chart-tick">([^<]*)</text>')
    return [(float(x), text) for x, anchor, text in re.findall(pattern, svg)
            if anchor == charts.ANCHOR_RIGHT]


def _vertical_charts() -> list[tuple[str, str]]:
    bars = [charts.Bar(label="الف", value=41.0), charts.Bar(label="ب", value=7.5),
            charts.Bar(label="پ", value=0.4)]
    return [
        ("columns", charts.columns(bars, unit=" م")),
        ("columns/میلیارد", charts.columns(bars, unit=" میلیارد", decimals=1)),
        ("histogram", charts.histogram([(index * 9.0, 40 + index)
                                        for index in range(20)], unit=" میلیارد")),
        ("grouped", charts.grouped_bars(
            ["الف", "ب"],
            [("یک", [41.0, 7.5], "var(--chart-soft)"),
             ("دو", [38.0, 6.0], "var(--chart-1)")],
            unit=" میلیارد", decimals=1)),
    ]


@pytest.mark.parametrize("name,svg", _vertical_charts(),
                         ids=[name for name, _ in _vertical_charts()])
def test_value_axis_labels_never_enter_the_plot(name, svg):
    """برچسب محور مقدار باید بیرون از ناحیهٔ رسم تمام شود.

    این آزمون همان باگی را می‌گیرد که در صفحهٔ تحلیل دیده شد: برچسبی مثل
    «۱۰٫۰ میلیارد» از x=۱۲ تا x=۷۰ می‌رسید در حالی که ناحیهٔ رسم از x=۱۸
    شروع می‌شد؛ نتیجه این بود که خطوط راهنما از روی متن عبور می‌کردند.
    """
    plot_left = _plot_left(svg)
    labels = _value_axis_labels(svg)
    assert labels, f"{name}: هیچ برچسبی روی محور مقدار نیست"
    for x, text in labels:
        assert x <= plot_left - 4, f"{name}: برچسب «{text}» وارد ناحیهٔ رسم شده"
        assert x - charts._text_width(text) >= 0, (
            f"{name}: برچسب «{text}» از لبهٔ چپ قاب بیرون زده")


def test_histogram_labels_clear_the_first_bucket():
    """میله‌های هیستوگرام کل ناحیهٔ رسم را پر می‌کنند؛ پس برچسب‌ها باید
    کاملاً بیرون از آن بنشینند، وگرنه عدد محور روی نخستین سطل می‌افتد."""
    svg = charts.histogram([(index * 30.0, 200 - index * 8)
                            for index in range(24)], unit=" میلیارد")
    plot_left = _plot_left(svg)
    buckets = [float(re.search(r'x="([\d.]+)"', r).group(1)) for r in _rects(svg)]
    assert min(buckets) == pytest.approx(plot_left, abs=1.0)
    for x, text in _value_axis_labels(svg):
        assert x <= plot_left - 4, "برچسب محور روی نخستین سطل افتاده"


def test_gutter_grows_with_the_label():
    """حاشیهٔ محور باید از پهن‌ترین برچسب حساب شود، نه از یک عدد ثابت."""
    short = _plot_left(charts.columns([charts.Bar(label="الف", value=10)], unit=" م"))
    long = _plot_left(charts.columns([charts.Bar(label="الف", value=10)],
                                     unit=" میلیارد", decimals=1))
    assert long > short


@pytest.mark.parametrize("name,svg", _vertical_charts(),
                         ids=[name for name, _ in _vertical_charts()])
def test_vertical_charts_stay_inside_the_canvas(name, svg):
    """قاعدهٔ قاب روی نمودارهای عمودی هم برقرار است."""
    assert _escaping_rects(svg) == [], f"{name}: میله از قاب بیرون زده"
    width, _ = _viewbox(svg)
    for x, text in _value_axis_labels(svg):
        assert 0 <= x <= width
