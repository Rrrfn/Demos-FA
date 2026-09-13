# -*- coding: utf-8 -*-
"""نمودارها به شکل SVG ساخته‌شده روی سرور.

هیچ کتابخانهٔ نموداری در مرورگر اجرا نمی‌شود. هر نمودار اینجا به یک رشتهٔ SVG
تبدیل می‌شود که با همان CSS صفحه استایل می‌گیرد؛ نتیجه این است که صفحهٔ تحلیل
بدون یک بایت JavaScript اضافه و بدون هیچ درخواست شبکه‌ای برای دادهٔ نمودار
رندر می‌شود.

سه قاعده در این ماژول رعایت می‌شود، و هر سه از باگ‌های واقعی آمده‌اند:

۱) **سقف محور هرگز زیر بزرگ‌ترین داده نمی‌افتد.** اگر بیفتد، بلندی میله از
   بلندی محور بیشتر می‌شود و میله با مختصات منفی از قاب بیرون می‌زند.

۲) **لنگر متن آگاه به جهت است.** بوم SVG داخل سند ``dir="rtl"`` قرار می‌گیرد و
   ``direction`` را از ارث می‌برد؛ در آن حالت معنای ``text-anchor`` آینه
   می‌شود. ثابت‌های ``ANCHOR_*`` همان چیزی را می‌گویند که منظورمان است.

۳) **حاشیهٔ محور مقدار از پهنای واقعی برچسب حساب می‌شود.** با یک عدد ثابت،
   برچسب بلندتری مثل «بالای ۸۰٪» وارد ناحیهٔ رسم می‌شود و خطوط راهنما از روی
   متن عبور می‌کنند.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .labels import fa_number, fa_percent

DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 300

#: لنگر متن — با توجه به راست‌به‌چپ بودن سند.
#:
#: در سند راست‌به‌چپ، ``text-anchor="start"`` لبهٔ راست متن را روی مختصات
#: می‌نشاند و متن به چپ می‌رود؛ ``end`` برعکس. نوشتن این ثابت‌ها به‌جای رشتهٔ
#: خام، جلوی این اشتباه را می‌گیرد. ترتیب حروف فارسی در هر دو حالت درست است و
#: تنها جای متن جابه‌جا می‌شود.
ANCHOR_RIGHT = "start"     # لبهٔ راست متن روی لنگر — متن به چپ می‌رود
ANCHOR_LEFT = "end"        # لبهٔ چپ متن روی لنگر — متن به راست می‌رود
ANCHOR_CENTER = "middle"   # وسط متن روی لنگر — مستقل از جهت


@dataclass(frozen=True)
class Bar:
    """یک میله: برچسب، مقدار، و توضیح اختیاری برای راهنمای شناور."""

    label: str
    value: float
    hint: str = ""
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
        # جهت صریح نوشته می‌شود تا رفتار نمودار به CSS یا صاحب‌صفحه وابسته نباشد.
        head = (f'<svg class="chart" viewBox="0 0 {self.width} {self.height}" '
                f'direction="rtl" preserveAspectRatio="xMidYMid meet" {aria}>')
        if self.title:
            head += f"<title>{_esc(self.title)}</title>"
        if self.description:
            head += f"<desc>{_esc(self.description)}</desc>"
        return head + "".join(self.parts) + "</svg>"


def _esc(text: object) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _char_width(char: str) -> float:
    """پهنای تقریبی یک نویسه در واحد viewBox (اندازهٔ قلم ۱۱ تا ۱۲)."""
    code = ord(char)
    if 0x06F0 <= code <= 0x06F9 or 0x0660 <= code <= 0x0669:
        return 6.0                      # ارقام فارسی و عربی
    if char.isdigit():
        return 6.1
    if char in "٬,٫.":
        return 3.0
    if char in "٪%":
        return 7.5
    if char == " ":
        return 3.5
    return 6.4 if code < 128 else 6.6   # لاتین / فارسی


def _text_width(text: str) -> float:
    return sum(_char_width(char) for char in text)


def _value_gutter(labels: list[str], *, minimum: int = 46,
                  maximum: int = 150) -> int:
    """حاشیهٔ کنار نمودار برای برچسب‌های محور مقدار.

    تخمین عمداً **دست‌بالا** است: زیادیِ حاشیه فقط چند واحد فضای خالی است، ولی
    کم‌آوردنش متن را وارد ناحیهٔ رسم می‌کند و خطوط راهنما از رویش عبور می‌کنند.
    """
    widest = max((_text_width(text) for text in labels), default=0.0)
    return int(min(maximum, max(minimum, widest + 14)))


def _ticks(top: float, count: int = 4) -> list[float]:
    """خطوط راهنمای محور مقدار — عددهای گرد و خوانا.

    **قاعدهٔ حیاتی:** آخرین خط راهنما هرگز از بزرگ‌ترین مقدار داده کوچک‌تر
    نیست. اگر باشد، میله از قاب بیرون می‌زند. سقف محور از گردکردن *رو به بالا*
    می‌آید، پس نه کوتاه می‌افتد و نه بیهوده باز می‌ماند.
    """
    if top <= 0:
        return [0.0]
    rough = top / count
    magnitude = 10 ** math.floor(math.log10(rough)) if rough > 0 else 1
    step = magnitude * 10
    for factor in (1, 2, 2.5, 5, 10):
        candidate = magnitude * factor
        if candidate >= rough:
            step = candidate
            break
    axis = math.ceil(top / step) * step
    return [index * step for index in range(int(round(axis / step)) + 1)]


def _label(value: float, unit: str, *, decimals: int = 0) -> str:
    text = fa_number(value, decimals=decimals)
    return f"{text}{unit}" if unit else text


# ------------------------------------------------------------------ میله‌ای افقی
def horizontal_bars(bars: list[Bar], *, width: int = DEFAULT_WIDTH,
                    row_height: int = 34, label_width: int = 150,
                    unit: str = "", decimals: int = 0,
                    color: str = "var(--chart-1)",
                    title: str = "", show_values: bool = True) -> str:
    """نمودار میله‌ای افقی — برچسب راست، میله به سمت چپ.

    عدد هر میله *بیرون* سر آن می‌نشیند. دلیلش فقط زیبایی نیست: رنگ میله تیره
    است و متن تیره روی آن خوانده نمی‌شود، و عدد در میله‌های کوتاه اصلاً جا
    نمی‌گیرد.
    """
    rows = [bar for bar in bars if bar.value is not None]
    if not rows:
        return ""

    top = max(abs(bar.value) for bar in rows) or 1.0
    ticks = _ticks(top)
    axis = max(max(ticks), top)
    pad_top = 30
    pad_bottom = 26
    height = pad_top + row_height * len(rows) + pad_bottom
    displays = [bar.display or _label(bar.value, unit, decimals=decimals)
                for bar in rows]
    tick_texts = [_label(value, unit, decimals=decimals) for value in ticks]
    value_gutter = max(
        48,
        int(max((_text_width(text) for text in displays), default=0.0) + 14),
        int(max((_text_width(text) for text in tick_texts), default=0.0) / 2 + 10),
    )
    plot_left = 14 + value_gutter
    plot_right = width - label_width

    frame = Frame(width=width, height=height, title=title)
    span = max(1, plot_right - plot_left)

    for value in ticks:
        x = plot_right - (value / axis) * span
        frame.add(
            f'<line x1="{x:.1f}" y1="{pad_top - 8}" x2="{x:.1f}" '
            f'y2="{height - pad_bottom + 4}" stroke="var(--chart-grid)" '
            f'stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{x:.1f}" y="{height - pad_bottom + 20}" '
            f'text-anchor="{ANCHOR_CENTER}" class="chart-tick">'
            f"{_esc(_label(value, unit, decimals=decimals))}</text>"
        )

    for index, bar in enumerate(rows):
        y = pad_top + index * row_height
        bar_span = max(2.0, (abs(bar.value) / axis) * span)
        x = plot_right - bar_span
        fill = bar.color or color
        tip = bar.hint or f"{bar.label}: {_label(bar.value, unit, decimals=decimals)}"
        # عدد سر میله وقتی نوشته می‌شود که مقیاس، عدد معناداری داشته باشد.
        # در نمودار واژگان متمایزکننده، عدد یک «امتیاز نسبی» است و نوشتنش به
        # شکل درصد، همان ادعای بی‌پایه‌ای است که این پروژه از آن پرهیز می‌کند؛
        # پس آنجا فقط طول میله نشان داده می‌شود.
        value_text = ("" if not show_values else
                      f'<text x="{x - 8:.1f}" y="{y + row_height / 2 + 5:.1f}" '
                      f'text-anchor="{ANCHOR_RIGHT}" class="chart-value">'
                      f"{_esc(bar.display or _label(bar.value, unit, decimals=decimals))}"
                      f"</text>")
        frame.add(
            f'<g class="chart-row"><title>{_esc(tip)}</title>'
            f'<rect x="{x:.1f}" y="{y + 6:.1f}" width="{bar_span:.1f}" '
            f'height="{row_height - 14}" rx="3" fill="{fill}"/>'
            f'<text x="{width - 8}" y="{y + row_height / 2 + 5:.1f}" '
            f'text-anchor="{ANCHOR_RIGHT}" class="chart-label">'
            f"{_esc(bar.label)}</text>{value_text}</g>"
        )
    return frame.render()


# ------------------------------------------------------------------ ستونی عمودی
def columns(bars: list[Bar], *, width: int = DEFAULT_WIDTH,
            height: int = DEFAULT_HEIGHT, unit: str = "",
            decimals: int = 0, color: str = "var(--chart-1)",
            title: str = "", rotate_labels: bool = False,
            show_values: bool = True) -> str:
    """نمودار ستونی — دسته‌ها از راست به چپ چیده می‌شوند.

    عدد هر ستون بالای آن می‌نشیند و حاشیهٔ بالای نمودار عمداً باز است تا
    بلندترین ستون هم جای عددش را داشته باشد.
    """
    rows = [bar for bar in bars if bar.value is not None]
    if not rows:
        return ""

    top = max(bar.value for bar in rows) or 1.0
    ticks = _ticks(top)
    axis = max(max(ticks), top)
    pad_top = 30
    pad_bottom = 56 if rotate_labels else 38
    gutter = _value_gutter(
        [_label(value, unit, decimals=decimals) for value in ticks])
    pad_side = gutter + 8
    plot_bottom = height - pad_bottom
    span = plot_bottom - pad_top

    frame = Frame(width=width, height=height, title=title)
    for value in ticks:
        y = plot_bottom - (value / axis) * span
        frame.add(
            f'<line x1="{gutter}" y1="{y:.1f}" x2="{width - 8}" '
            f'y2="{y:.1f}" stroke="var(--chart-grid)" stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{gutter - 8}" y="{y + 4:.1f}" '
            f'text-anchor="{ANCHOR_RIGHT}" class="chart-tick">'
            f"{_esc(_label(value, unit, decimals=decimals))}</text>"
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
        # عدد بالای ستون؛ در عرض‌های تنگ حذف می‌شود تا عددها به هم نچسبند.
        if show_values and slot >= 34:
            frame.add(
                f'<text x="{center:.1f}" y="{y - 7:.1f}" '
                f'text-anchor="{ANCHOR_CENTER}" class="chart-value">'
                f"{_esc(bar.display or _label(bar.value, unit, decimals=decimals))}"
                f"</text>"
            )
        transform = (f' transform="rotate(40 {center:.1f} {plot_bottom + 18:.1f})"'
                     if rotate_labels else "")
        anchor = ANCHOR_RIGHT if rotate_labels else ANCHOR_CENTER
        frame.add(
            f'<text x="{center:.1f}" y="{plot_bottom + (18 if rotate_labels else 22):.1f}" '
            f'text-anchor="{anchor}"{transform} class="chart-label">'
            f"{_esc(bar.label)}</text>"
        )
    frame.add(
        f'<line x1="{gutter}" y1="{plot_bottom:.1f}" x2="{width - 8}" '
        f'y2="{plot_bottom:.1f}" stroke="var(--chart-axis)" stroke-width="1"/>'
    )
    return frame.render()


# ------------------------------------------------------------------ میله‌های گروهی
def grouped_bars(categories: list[str], series: list[tuple[str, list[float], str]], *,
                 width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
                 unit: str = "", decimals: int = 1,
                 title: str = "", rotate_labels: bool = False) -> str:
    """چند سری میله کنار هم برای هر دسته.

    برای مقایسهٔ همزمان سهم سه کلاس در هر ماه، یا کنار هم گذاشتن معیارهای
    چند مدل. میله‌های یک گروه از راست به چپ همان ترتیب ``series`` می‌نشینند.
    """
    if not categories or not series:
        return ""

    top = max((value for _, values, _ in series for value in values), default=0.0) or 1.0
    ticks = _ticks(top)
    axis = max(max(ticks), top)
    pad_top = 30
    pad_bottom = 58 if rotate_labels else 44
    gutter = _value_gutter(
        [_label(value, unit, decimals=decimals) for value in ticks])
    pad_side = gutter + 8
    plot_bottom = height - pad_bottom
    span = plot_bottom - pad_top

    frame = Frame(width=width, height=height, title=title)
    for value in ticks:
        y = plot_bottom - (value / axis) * span
        frame.add(
            f'<line x1="{gutter}" y1="{y:.1f}" x2="{width - 8}" y2="{y:.1f}" '
            f'stroke="var(--chart-grid)" stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{gutter - 8}" y="{y + 4:.1f}" '
            f'text-anchor="{ANCHOR_RIGHT}" class="chart-tick">'
            f"{_esc(_label(value, unit, decimals=decimals))}</text>"
        )

    slot = (width - pad_side - 8) / len(categories)
    bars_total = len(series)
    bar_width = max(6.0, min(38.0, (slot * 0.72) / bars_total))

    for index, category in enumerate(categories):
        right = width - 8 - index * slot
        left = right - slot
        group_center = (left + right) / 2
        group_width = bar_width * bars_total
        for offset, (name, values, fill) in enumerate(series):
            value = values[index] if index < len(values) else 0.0
            # اولین سری در راست‌ترین جای گروه می‌نشیند.
            x = group_center + group_width / 2 - (offset + 1) * bar_width
            bar_height = max(0.0, (value / axis) * span)
            y = plot_bottom - bar_height
            hint = f"{category} — {name}: {_label(value, unit, decimals=decimals)}"
            if value > 0:
                frame.add(
                    f'<g class="chart-row"><title>{_esc(hint)}</title>'
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 2:.1f}" '
                    f'height="{bar_height:.1f}" rx="3" fill="{fill}"/></g>'
                )
        transform = (f' transform="rotate(40 {group_center:.1f} {plot_bottom + 18:.1f})"'
                     if rotate_labels else "")
        anchor = ANCHOR_RIGHT if rotate_labels else ANCHOR_CENTER
        frame.add(
            f'<text x="{group_center:.1f}" '
            f'y="{plot_bottom + (18 if rotate_labels else 22):.1f}" '
            f'text-anchor="{anchor}"{transform} class="chart-label">'
            f"{_esc(category)}</text>"
        )

    frame.add(
        f'<line x1="{gutter}" y1="{plot_bottom:.1f}" x2="{width - 8}" '
        f'y2="{plot_bottom:.1f}" stroke="var(--chart-axis)" stroke-width="1"/>'
    )
    return frame.render()


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
    axis = max(max(ticks), float(top))
    pad_top = 16
    pad_bottom = 34
    #: میله‌ها کل ناحیهٔ رسم را پر می‌کنند، پس برچسب محور مقدار حتماً باید کامل
    #: بیرون از آن بنشیند؛ وگرنه روی نخستین سطل می‌افتد.
    plot_left = _value_gutter([fa_number(value) for value in ticks])
    plot_bottom = height - pad_bottom
    span = plot_bottom - pad_top
    plot_width = width - plot_left - 8

    frame = Frame(width=width, height=height, title=title)
    for value in ticks:
        y = plot_bottom - (value / axis) * span
        frame.add(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{width - 8}" y2="{y:.1f}" '
            f'stroke="var(--chart-grid)" stroke-width="1"/>'
        )
        frame.add(
            f'<text x="{plot_left - 8}" y="{y + 4:.1f}" '
            f'text-anchor="{ANCHOR_RIGHT}" class="chart-tick">'
            f"{_esc(fa_number(value))}</text>"
        )

    slot = plot_width / len(rows)
    for index, (x_value, count) in enumerate(rows):
        bar_height = max(0.0, (count / axis) * span)
        y = plot_bottom - bar_height
        x = plot_left + index * slot
        frame.add(
            f'<g class="chart-row"><title>{_esc(_label(x_value, unit, decimals=x_decimals))}'
            f" — {_esc(fa_number(count))} نمونه</title>"
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(1.0, slot - 1):.1f}" '
            f'height="{bar_height:.1f}" fill="{color}"/></g>'
        )
        if index % max(1, label_every) == 0:
            frame.add(
                f'<text x="{x + slot / 2:.1f}" y="{plot_bottom + 20:.1f}" '
                f'text-anchor="{ANCHOR_CENTER}" class="chart-tick">'
                f"{_esc(_label(x_value, unit, decimals=x_decimals))}</text>"
            )
    frame.add(
        f'<line x1="{plot_left}" y1="{plot_bottom:.1f}" x2="{width - 8}" '
        f'y2="{plot_bottom:.1f}" stroke="var(--chart-axis)" stroke-width="1"/>'
    )
    return frame.render()


# ------------------------------------------------------------------ نوار سهم
def stacked_share(parts: list[tuple[str, float, str]], *, width: int = 640,
                  bar_height: int = 22, title: str = "") -> str:
    """سهم هر بخش از کل، به شکل یک نوار افقی تقسیم‌شده.

    برای ترکیب برچسب‌ها در تحلیل گروهی: چند درصد مثبت، چند درصد خنثی، چند
    درصد منفی. مجموع نسبی است، پس تقسیم بر مجموع واقعی انجام می‌شود.
    """
    total = sum(max(0.0, value) for _, value, _ in parts) or 1.0
    height = bar_height + 34
    frame = Frame(width=width, height=height, title=title)
    x = width
    for index, (label, value, color) in enumerate(parts):
        share = max(0.0, value) / total
        span = share * width
        if span < 0.4:
            continue
        x -= span
        frame.add(
            f'<g class="chart-row"><title>{_esc(label)}: '
            f'{_esc(fa_percent(share, decimals=1))}</title>'
            f'<rect x="{x:.1f}" y="0" width="{span:.1f}" height="{bar_height}" '
            f'fill="{color}" rx="3"/></g>'
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
