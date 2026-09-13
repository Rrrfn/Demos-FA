# -*- coding: utf-8 -*-
"""نمودارها به شکل SVG ساخته‌شده روی سرور.

پیش از این نمودارها با Altair ساخته می‌شدند. Altair هر نمودار را به یک
مشخصات Vega-Lite تبدیل می‌کند و مرورگر باید برای رسم آن حدود یک مگابایت
JavaScript اضافه دانلود و اجرا کند؛ روی اتصال کند و ماشین ضعیف، همان
کتابخانه بیشتر از خود داده طول می‌کشد. اینجا نمودار مستقیماً به SVG تبدیل
می‌شود: بدون JavaScript، بدون پرس‌وجوی سمت مرورگر، و قابل استایل با همان CSS
صفحه.

سه قاعده رعایت می‌شود:

۱) **هیچ داده‌ای ساخته نمی‌شود.** ورودی هر تابع، نقاط واقعی است؛ اگر خالی
   باشد SVG خالی برمی‌گردد و قالب پیام مناسب نشان می‌دهد.

۲) **همه‌چیز از متغیرهای CSS رنگ می‌گیرد.** رنگ‌ها در SVG به‌صورت
   ``var(--…)`` نوشته می‌شوند، پس تغییر پوسته، نمودارها را هم عوض می‌کند.

۳) **چیدمان راست‌به‌چپ.** در نمودار میله‌ای افقی، برچسب سمت راست می‌نشیند و
   میله به سمت چپ رشد می‌کند؛ در نمودار ستونی، دسته‌ها از راست به چپ
   می‌آیند. این همان ترتیبی است که چشم فارسی‌زبان انتظار دارد.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .labels import fa_number, fa_percent

#: اندازه‌های پیش‌فرض در واحد viewBox. مقیاس واقعی با CSS انجام می‌شود.
DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 320


@dataclass(frozen=True)
class Bar:
    """یک میله: برچسب، مقدار، و توضیح اختیاری برای راهنمای شناور."""

    label: str
    value: float
    hint: str = ""
    #: مقدار نمایشی روی میله — اگر خالی باشد از ``value`` ساخته می‌شود.
    display: str = ""
    color: str = ""


@dataclass
class Frame:
    """بوم SVG — جمع‌کردن اجزا و تحویل رشتهٔ نهایی."""

    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    title: str = ""
    description: str = ""
    parts: list[str] = field(default_factory=list)

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def render(self) -> str:
        label = self.title or self.description
        aria = (f'role="img" aria-label="{_esc(label)}"' if label
                else 'role="presentation" aria-hidden="true"')
        head = (f'<svg class="chart" viewBox="0 0 {self.width} {self.height}" '
                f'preserveAspectRatio="xMidYMid meet" {aria}>')
        if self.title:
            head += f"<title>{_esc(self.title)}</title>"
        if self.description:
            head += f"<desc>{_esc(self.description)}</desc>"
        return head + "".join(self.parts) + "</svg>"


def _esc(text: object) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _ticks(top: float, count: int = 4) -> list[float]:
    """خطوط راهنمای محور مقدار — عددهای گرد و خوانا."""
    if top <= 0:
        return [0.0]
    step = top / count
    magnitude = 10 ** math.floor(math.log10(step)) if step > 0 else 1
    for factor in (1, 2, 2.5, 5, 10):
        candidate = magnitude * factor
        if candidate >= step:
            step = candidate
            break
    values = [step * index for index in range(count + 1)]
    return [value for value in values if value <= top * 1.0001] or [top]


def _label(value: float, unit: str, *, decimals: int = 0) -> str:
    """برچسب عددی محور با واحد و رقم فارسی."""
    text = fa_number(value, decimals=decimals) if decimals else fa_number(value)
    return f"{text}{unit}" if unit else text


# ------------------------------------------------------------------ میله‌ای افقی
def horizontal_bars(bars: list[Bar], *, width: int = DEFAULT_WIDTH,
                    row_height: int = 34, label_width: int = 168,
                    unit: str = "", decimals: int = 0,
                    color: str = "var(--chart-1)",
                    title: str = "", value_header: str = "") -> str:
    """نمودار میله‌ای افقی — برچسب راست، میله به سمت چپ.

    مناسب برای مقایسهٔ مناطق یا ویژگی‌ها، جایی که برچسب‌ها متنی‌اند.
    """
    rows = [bar for bar in bars if bar.value is not None]
    if not rows:
        return ""

    top = max(bar.value for bar in rows) or 1.0
    ticks = _ticks(top)
    axis = max(ticks)
    pad_top = 30
    pad_bottom = 26
    height = pad_top + row_height * len(rows) + pad_bottom
    plot_left = 16
    plot_right = width - label_width

    frame = Frame(width=width, height=height, title=title or value_header)
    span = max(1, plot_right - plot_left)

    # خطوط راهنما زیر میله‌ها کشیده می‌شوند تا خوانایی حفظ شود.
    for value in ticks:
        x = plot_right - (value / axis) * span
        frame.add(
            f'<line x1="{x:.1f}" y1="{pad_top - 8}" x2="{x:.1f}" '
            f'y2="{height - pad_bottom + 4}" stroke="var(--chart-grid)" '
            f'stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{x:.1f}" y="{height - pad_bottom + 20}" '
            f'text-anchor="middle" class="chart-tick">'
            f"{_esc(_label(value, unit, decimals=decimals))}</text>"
        )

    for index, bar in enumerate(rows):
        y = pad_top + index * row_height
        bar_span = max(2.0, (bar.value / axis) * span)
        x = plot_right - bar_span
        fill = bar.color or color
        tip = bar.hint or f"{bar.label}: {_label(bar.value, unit, decimals=decimals)}"
        frame.add(
            f'<g class="chart-row"><title>{_esc(tip)}</title>'
            f'<rect x="{x:.1f}" y="{y + 6:.1f}" width="{bar_span:.1f}" '
            f'height="{row_height - 14}" rx="3" fill="{fill}"/>'
            f'<text x="{width - 8}" y="{y + row_height / 2 + 5:.1f}" '
            f'text-anchor="end" class="chart-label">{_esc(bar.label)}</text>'
            f'<text x="{plot_right - 8}" y="{y + row_height / 2 + 5:.1f}" '
            f'text-anchor="end" class="chart-value">'
            f"{_esc(bar.display or _label(bar.value, unit, decimals=decimals))}"
            f"</text></g>"
        )
    return frame.render()


# ------------------------------------------------------------------ ستونی عمودی
def columns(bars: list[Bar], *, width: int = DEFAULT_WIDTH,
            height: int = DEFAULT_HEIGHT, unit: str = "",
            decimals: int = 0, color: str = "var(--chart-1)",
            title: str = "", rotate_labels: bool = False) -> str:
    """نمودار ستونی — دسته‌ها از راست به چپ چیده می‌شوند."""
    rows = [bar for bar in bars if bar.value is not None]
    if not rows:
        return ""

    top = max(bar.value for bar in rows) or 1.0
    ticks = _ticks(top)
    axis = max(ticks)
    pad_top = 16
    pad_bottom = 56 if rotate_labels else 38
    pad_side = 62
    plot_bottom = height - pad_bottom
    span = plot_bottom - pad_top

    frame = Frame(width=width, height=height, title=title)
    for value in ticks:
        y = plot_bottom - (value / axis) * span
        frame.add(
            f'<line x1="{pad_side - 44}" y1="{y:.1f}" x2="{width - 8}" '
            f'y2="{y:.1f}" stroke="var(--chart-grid)" stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{pad_side - 50}" y="{y + 4:.1f}" text-anchor="end" '
            f'class="chart-tick">{_esc(_label(value, unit, decimals=decimals))}</text>'
        )

    slot = (width - pad_side - 8) / len(rows)
    bar_width = max(6.0, min(48.0, slot * 0.62))

    for index, bar in enumerate(rows):
        # دستهٔ نخست در راست‌ترین جایگاه می‌نشیند.
        right = width - 8 - index * slot
        left = right - slot
        center = (left + right) / 2
        bar_height = max(1.0, (bar.value / axis) * span)
        y = plot_bottom - bar_height
        tip = bar.hint or f"{bar.label}: {_label(bar.value, unit, decimals=decimals)}"
        if bar.value > 0:
            frame.add(
                f'<g class="chart-row"><title>{_esc(tip)}</title>'
                f'<rect x="{center - bar_width / 2:.1f}" y="{y:.1f}" '
                f'width="{bar_width:.1f}" height="{bar_height:.1f}" rx="3" '
                f'fill="{bar.color or color}"/></g>'
            )
        transform = (f' transform="rotate(-40 {center:.1f} {plot_bottom + 18:.1f})"'
                     if rotate_labels else "")
        anchor = "end" if rotate_labels else "middle"
        frame.add(
            f'<text x="{center:.1f}" y="{plot_bottom + (18 if rotate_labels else 22):.1f}" '
            f'text-anchor="{anchor}"{transform} class="chart-label">'
            f"{_esc(bar.label)}</text>"
        )
    frame.add(
        f'<line x1="{pad_side - 44}" y1="{plot_bottom:.1f}" x2="{width - 8}" '
        f'y2="{plot_bottom:.1f}" stroke="var(--chart-axis)" stroke-width="1"/>'
    )
    return frame.render()


# ------------------------------------------------------------------ میله‌های گروهی
def grouped_bars(categories: list[str], series: list[tuple[str, list[float], str]], *,
                 width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
                 unit: str = "", decimals: int = 1,
                 title: str = "", name_header: str = "") -> str:
    """چند سری میله کنار هم برای هر دسته — برای مقایسهٔ «قیمت آگهی در برابر برآورد»."""
    if not categories or not series:
        return ""

    top = max((value for _, values, _ in series for value in values), default=0.0) or 1.0
    ticks = _ticks(top)
    axis = max(ticks)
    pad_top = 16
    pad_bottom = 46
    pad_side = 64
    plot_bottom = height - pad_bottom
    span = plot_bottom - pad_top

    frame = Frame(width=width, height=height, title=title)
    for value in ticks:
        y = plot_bottom - (value / axis) * span
        frame.add(
            f'<line x1="{pad_side - 46}" y1="{y:.1f}" x2="{width - 8}" y2="{y:.1f}" '
            f'stroke="var(--chart-grid)" stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{pad_side - 52}" y="{y + 4:.1f}" text-anchor="end" '
            f'class="chart-tick">{_esc(_label(value, unit, decimals=decimals))}</text>'
        )

    slot = (width - pad_side - 8) / len(categories)
    bars_total = len(series)
    bar_width = max(6.0, min(38.0, (slot * 0.7) / bars_total))

    for index, category in enumerate(categories):
        right = width - 8 - index * slot
        left = right - slot
        group_center = (left + right) / 2
        group_width = bar_width * bars_total
        for offset, (_, values, color) in enumerate(series):
            value = values[index] if index < len(values) else 0.0
            # اولین سری در راست‌ترین جای گروه می‌نشیند.
            x = group_center + group_width / 2 - (offset + 1) * bar_width
            bar_height = max(1.0, (value / axis) * span)
            y = plot_bottom - bar_height
            label = series[offset][0]
            hint = f"{category} — {label}: {_label(value, unit, decimals=decimals)}"
            frame.add(
                f'<g class="chart-row"><title>{_esc(hint)}</title>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 2:.1f}" '
                f'height="{bar_height:.1f}" rx="3" fill="{color}"/></g>'
            )
        frame.add(
            f'<text x="{group_center:.1f}" y="{plot_bottom + 22:.1f}" '
            f'text-anchor="middle" class="chart-label">{_esc(category)}</text>'
        )

    frame.add(
        f'<line x1="{pad_side - 46}" y1="{plot_bottom:.1f}" x2="{width - 8}" '
        f'y2="{plot_bottom:.1f}" stroke="var(--chart-axis)" stroke-width="1"/>'
    )
    return frame.render()


def legend(items: list[tuple[str, str]]) -> str:
    """راهنمای رنگ — (برچسب، رنگ)."""
    if not items:
        return ""
    chips = "".join(
        f'<span class="legend-item"><i style="background:{color}"></i>{_esc(label)}</span>'
        for label, color in items
    )
    return f'<div class="legend">{chips}</div>'


# ------------------------------------------------------------------ هیستوگرام
def histogram(points: list[tuple[float, int]], *, width: int = DEFAULT_WIDTH,
              height: int = DEFAULT_HEIGHT, unit: str = "",
              x_decimals: int = 0, title: str = "",
              label_every: int = 4, color: str = "var(--chart-2)") -> str:
    """توزیع — میله‌ها چسبیده و محور افقی پیوسته."""
    rows = [(float(x), int(y)) for x, y in points if y is not None]
    if not rows:
        return ""

    top = max(value for _, value in rows) or 1
    ticks = _ticks(float(top))
    axis = max(ticks)
    pad_top = 16
    pad_bottom = 34
    pad_side = 56
    plot_bottom = height - pad_bottom
    span = plot_bottom - pad_top
    plot_left = pad_side - 38
    plot_width = width - plot_left - 8

    frame = Frame(width=width, height=height, title=title)
    for value in ticks:
        y = plot_bottom - (value / axis) * span
        frame.add(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{width - 8}" y2="{y:.1f}" '
            f'stroke="var(--chart-grid)" stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{pad_side - 44}" y="{y + 4:.1f}" text-anchor="end" '
            f'class="chart-tick">{_esc(fa_number(value))}</text>'
        )

    slot = plot_width / len(rows)
    for index, (x_value, count) in enumerate(rows):
        bar_height = max(0.0, (count / axis) * span)
        y = plot_bottom - bar_height
        x = plot_left + index * slot
        frame.add(
            f'<g class="chart-row"><title>{_esc(_label(x_value, unit, decimals=x_decimals))}'
            f" — {_esc(fa_number(count))} آگهی</title>"
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(1.0, slot - 1):.1f}" '
            f'height="{bar_height:.1f}" fill="{color}"/></g>'
        )
        if index % max(1, label_every) == 0:
            frame.add(
                f'<text x="{x + slot / 2:.1f}" y="{plot_bottom + 20:.1f}" '
                f'text-anchor="middle" class="chart-tick">'
                f"{_esc(_label(x_value, unit, decimals=x_decimals))}</text>"
            )
    frame.add(
        f'<line x1="{plot_left}" y1="{plot_bottom:.1f}" x2="{width - 8}" '
        f'y2="{plot_bottom:.1f}" stroke="var(--chart-axis)" stroke-width="1"/>'
    )
    return frame.render()


# ------------------------------------------------------------------ نمودار پله‌ای
def stacked_share(parts: list[tuple[str, float, str]], *, width: int = 640,
                  bar_height: int = 22, title: str = "") -> str:
    """سهم هر بخش از کل، به شکل یک نوار افقی تقسیم‌شده.

    برای نمایش پوشش بازهٔ اطمینان («۷۷٫۵٪ از ۸۰٪ هدف») یا سهم مناطق از
    کاتالوگ. مجموع نسبی است، پس تقسیم بر مجموع واقعی انجام می‌شود.
    """
    total = sum(max(0.0, value) for _, value, _ in parts) or 1.0
    height = bar_height + 34
    frame = Frame(width=width, height=height, title=title)
    x = width
    for index, (label, value, color) in enumerate(parts):
        share = max(0.0, value) / total
        span = share * width
        x -= span
        if span < 0.4:
            continue
        frame.add(
            f'<g class="chart-row"><title>{_esc(label)}: '
            f'{_esc(fa_percent(share, decimals=1))}</title>'
            f'<rect x="{x:.1f}" y="0" width="{span:.1f}" height="{bar_height}" '
            f'fill="{color}" rx="{4 if index in (0, len(parts) - 1) else 0}"/></g>'
        )
    return frame.render()
