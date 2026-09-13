# -*- coding: utf-8 -*-
"""موتور نمودار — هندسهٔ واحد، دو رندرکننده.

چرا دو رندرکننده؟ رابط وب به SVG نیاز دارد (برداری، سبک، بدون کتابخانهٔ
مرورگر) و PDF به تصویر رستر (fpdf2 تصویر می‌فهمد، SVG نمی‌فهمد). اگر هر کدام
هندسهٔ خودش را حساب کند، دو نمودار متفاوت از یک داده درمی‌آید و کاربر دو
روایت می‌بیند. پس محاسبهٔ محور، مقیاس و برچسب **یک‌جا** انجام می‌شود و هر
رندرکننده فقط می‌کشد.

سه قاعدهٔ هندسی که در این ماژول تضمین شده‌اند و آزمون هم دارند:

۱) **سقف محور هرگز از بزرگ‌ترین داده کمتر نیست.** اگر کمتر باشد، میله از قاب
   بیرون می‌زند — دقیقاً همان چیزی که در نسخهٔ قبلی این پروژه دیده شد.

۲) **گزیر محور مقدار از پهنای واقعی بلندترین برچسب حساب می‌شود.** پهنای ثابت
   باعث می‌شود برچسب عددی مثل «۱۰٫۰ میلیارد» روی ناحیهٔ رسم برود و خطوط
   راهنما از روی متن عبور کنند.

۳) **جهت متن صریح است.** بوم SVG داخل سند راست‌به‌چپ، معنی ``text-anchor`` را
   آینه می‌کند؛ پس ``direction: ltr`` روی خود بوم گذاشته می‌شود و لنگرها
   دستی حساب می‌شوند. متن فارسی همچنان درست می‌نشیند چون شکل‌دهی حروف کار
   فونت است، نه جهت سند.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

from .labels import fa_compact, fa_number, to_persian_digits

#: اندازه‌های پایهٔ بوم SVG (واحد کاربر).
SVG_WIDTH = 720
SVG_HEIGHT = 320
SVG_BAR_HEIGHT = 90          #: ارتفاع هر ردیف در نمودار میله‌ای افقی
SVG_PAD = 18
#: سقف تعداد میله‌ای که برچسب محور افقی می‌گیرد؛ بیشتر از این، برچسب‌ها به هم
#: می‌چسبند و خواندنشان ناممکن می‌شود.
MAX_X_LABELS = 8


# ------------------------------------------------------------------ هندسه
def nice_ceiling(value: float) -> float:
    """سقف محور: عددی «گرد» که از مقدار داده کمتر نباشد.

    قاعدهٔ اول همین‌جا تضمین می‌شود: خروجی هرگز کمتر از ورودی نیست.
    """
    if value is None or value != value or value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10 ** exponent
    for step in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        candidate = step * base
        if candidate >= value * 0.999999:
            return candidate
    return 10 * base


def nice_floor(value: float) -> float:
    """کف محور برای دادهٔ منفی — آینهٔ ``nice_ceiling``."""
    if value is None or value != value or value >= 0:
        return 0.0
    return -nice_ceiling(abs(value))


def ticks(low: float, high: float, count: int = 5) -> list[float]:
    """مقادیر خطوط راهنما از ``low`` تا ``high``."""
    if high <= low:
        high = low + 1
    step = (high - low) / max(1, count)
    return [low + step * index for index in range(count + 1)]


def text_width_estimate(text: str, size: float = 12.0) -> float:
    """تخمین پهنای متن برای اندازه‌گیری گزیر محور.

    تخمین عمدی و محافظه‌کارانه است: هر نویسهٔ فارسی/رقم کمی پهن‌تر از میانگین
    فرض می‌شود تا گزیر همیشه کافی باشد. گزیر بزرگ‌تر از لازم فقط کمی فضای
    نمودار را کم می‌کند؛ گزیر کوچک، متن را روی میله می‌برد.
    """
    weight = 0.62
    return max(0.0, len(str(text)) * size * weight)


def gutter_width(labels: list[str], size: float = 12.0, padding: float = 12.0) -> float:
    """پهنای گزیر محور مقدار از بلندترین برچسب (قاعدهٔ دوم)."""
    if not labels:
        return padding + size
    return max(text_width_estimate(label, size) for label in labels) + padding


@dataclass
class Geometry:
    """هندسهٔ محاسبه‌شدهٔ یک نمودار — مشترک بین SVG و PNG."""

    width: float
    height: float
    left: float
    right: float
    top: float
    bottom: float
    low: float
    high: float
    value_ticks: list[float] = field(default_factory=list)
    #: برچسب‌های محور دسته (فارسی‌شده، آمادهٔ نمایش).
    labels: list[str] = field(default_factory=list)
    #: مقادیر اصلی، هم‌ترتیب با ``labels``.
    values: list[float] = field(default_factory=list)
    max_label: str = ""
    min_label: str = ""

    @property
    def plot_width(self) -> float:
        return max(1.0, self.right - self.left)

    @property
    def plot_height(self) -> float:
        return max(1.0, self.bottom - self.top)

    def ratio(self, value: float) -> float:
        """نسبت مقدار در بازهٔ محور (۰ تا ۱)."""
        span = self.high - self.low
        if span == 0:
            return 0.0
        return max(0.0, min(1.0, (value - self.low) / span))


def build_geometry(labels: list[str], values: list[float], *,
                   width: float = SVG_WIDTH, height: float = SVG_HEIGHT,
                   title_space: float = 0.0,
                   value_labels: list[str] | None = None) -> Geometry:
    """هندسهٔ یک نمودار میله‌ای/خطی — شامل همهٔ سه قاعدهٔ ماژول."""
    values = [0.0 if value is None or value != value else float(value)
              for value in values]
    peak = max(values) if values else 0.0
    trough = min(values) if values else 0.0
    high = nice_ceiling(peak)
    low = nice_floor(trough)
    marks = ticks(low, high, 5)

    #: برچسب محور مقدار روی علامت‌های محاسبه می‌شود (نه روی داده)، پس همان
    #: چیزی که کاربر می‌بیند در محاسبهٔ گزیر وارد شده است.
    shown = value_labels or [fa_compact(mark) for mark in marks]
    left = gutter_width(shown) + 6
    right = width - SVG_PAD - 8
    top = SVG_PAD + title_space
    bottom = height - 40
    return Geometry(
        width=width, height=height, left=left, right=right, top=top,
        bottom=bottom, low=low, high=high, value_ticks=marks,
        labels=[str(label) for label in labels], values=values,
        max_label=str(shown[-1] if shown else ""),
        min_label=str(shown[0] if shown else ""),
    )


def build_bar_geometry(labels: list[str], values: list[float], *,
                       width: float = SVG_WIDTH, row_height: float = SVG_BAR_HEIGHT) -> tuple[Geometry, list[float]]:
    """هندسهٔ نمودار میله‌ای افقی — همراه با «مرکز» هر ردیف.

    در نمودار افقی، پهنای ناحیهٔ رسم در محور مقدار خرج می‌شود، پس همان قاعدهٔ
    گزیر لازم است: گزیر محور مقدار بالا و گزیر برچسب دسته در سمت راست.
    """
    count = max(1, len(labels))
    height = SVG_PAD * 2 + count * row_height + 34
    peak = max(values) if values else 0.0
    high = nice_ceiling(peak)
    marks = ticks(0, high, 4)
    shown = [fa_compact(mark) for mark in marks]
    label_width = min(max((text_width_estimate(label, 12.0) for label in labels),
                          default=60.0) + 16, width * 0.34)
    left = gutter_width(shown) + 6
    right = width - SVG_PAD - label_width
    top = SVG_PAD
    bottom = top + count * row_height
    centers = [top + row_height * (index + 0.5) for index in range(count)]
    geometry = Geometry(
        width=width, height=height, left=left, right=right, top=top,
        bottom=bottom, low=0.0, high=high, value_ticks=marks,
        labels=[str(label) for label in labels], values=[float(v) for v in values],
        max_label=str(shown[-1] if shown else ""), min_label=str(shown[0] if shown else ""),
    )
    geometry.axis_label_width = label_width          # type: ignore[attr-defined]
    return geometry, centers


def build_line_geometry(labels: list[str], values: list[float], *,
                        width: float = SVG_WIDTH,
                        height: float = SVG_HEIGHT) -> Geometry:
    return build_geometry(labels, values, width=width, height=height,
                          title_space=8)


# ------------------------------------------------------------------ رنگ‌ها
def series_color(theme: dict, index: int) -> str:
    palette = theme.get("series") or ["#0e7c66"]
    return palette[index % len(palette)]


def _escape(text: object) -> str:
    """متن امن برای درج در SVG."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ------------------------------------------------------------------ SVG
def _svg_open(height: float, width: float = SVG_WIDTH,
              label: str = "") -> list[str]:
    """سربرگ بوم SVG — با جهت صریح چپ‌به‌راست (قاعدهٔ سوم)."""
    return [
        f'<svg class="chart" viewBox="0 0 {width:g} {height:g}" '
        f'width="100%" height="{height:g}" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="{_escape(label)}" '
        f'style="direction:ltr;display:block">',
    ]


def _grid_lines(geometry: Geometry, theme: dict, labels: list[str]) -> list[str]:
    parts: list[str] = []
    marks = geometry.value_ticks
    for index, mark in enumerate(marks):
        y = geometry.bottom - geometry.ratio(mark) * geometry.plot_height
        parts.append(
            f'<line x1="{geometry.left:.1f}" y1="{y:.1f}" '
            f'x2="{geometry.right:.1f}" y2="{y:.1f}" '
            f'stroke="{theme["line"]}" stroke-width="1"/>')
        #: برچسب با لنگر انتهایی و در فاصلهٔ امن از ناحیهٔ رسم.
        parts.append(
            f'<text x="{geometry.left - 8:.1f}" y="{y + 4:.1f}" '
            f'text-anchor="end" font-size="11" fill="{theme["muted"]}">'
            f'{_escape(labels[index])}</text>')
    return parts


def svg_bar(points: list[tuple[str, float, str]], geometry: Geometry,
            centers: list[float], theme: dict, *, title: str = "") -> str:
    """نمودار میله‌ای افقی.

    ``points`` سه‌گانه‌های ``(برچسب, مقدار, متن مقدار)`` است.
    """
    parts = _svg_open(geometry.height, geometry.width, title)
    offset = 26 if title else 0
    if title:
        parts.append(
            f'<text x="{geometry.width / 2:.1f}" y="20" text-anchor="middle" '
            f'font-size="13" font-weight="600" fill="{theme["ink"]}">'
            f'{_escape(title)}</text>')
    shift = offset
    grid = _grid_lines(geometry, theme, [fa_compact(mark) for mark in geometry.value_ticks])
    parts.extend(grid)
    bar_height = (geometry.bottom - geometry.top) / max(1, len(points)) * 0.56

    for index, (label, value, value_text) in enumerate(points):
        center = centers[index] + (0 if not shift else shift)
        length = geometry.ratio(value) * geometry.plot_width
        length = max(2.0, length)
        color = series_color(theme, index)
        parts.append(
            f'<rect x="{geometry.left:.1f}" y="{center - bar_height / 2:.1f}" '
            f'width="{length:.1f}" height="{bar_height:.1f}" rx="4" '
            f'fill="{color}"><title>{_escape(label)}: {_escape(value_text)}</title></rect>')
        #: متن مقدار بیرون از میله، سمت راست آن — با فاصله، نه روی میله.
        parts.append(
            f'<text x="{geometry.left + length + 6:.1f}" y="{center + 4:.1f}" '
            f'text-anchor="start" font-size="11" fill="{theme["muted"]}">'
            f'{_escape(value_text)}</text>')
        #: برچسب دسته در سمت راست ناحیهٔ رسم.
        parts.append(
            f'<text x="{geometry.right + 10:.1f}" y="{center + 4:.1f}" '
            f'text-anchor="start" font-size="12" fill="{theme["ink"]}">'
            f'{_escape(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_line(labels: list[str], values: list[float], geometry: Geometry,
             theme: dict, *, title: str = "", unit: str = "") -> str:
    """نمودار خطی با نقطه‌های واقعی — بدون هموارسازی ساختگی."""
    parts = _svg_open(geometry.height, geometry.width, title)
    if title:
        parts.append(
            f'<text x="{geometry.width / 2:.1f}" y="20" text-anchor="middle" '
            f'font-size="13" font-weight="600" fill="{theme["ink"]}">'
            f'{_escape(title)}</text>')
    parts.extend(_grid_lines(geometry, theme,
                             [fa_compact(mark) for mark in geometry.value_ticks]))

    count = len(values)
    if count == 0:
        parts.append("</svg>")
        return "".join(parts)
    step = geometry.plot_width / max(1, count - 1) if count > 1 else 0
    coords = []
    for index, value in enumerate(values):
        x = geometry.left + step * index if count > 1 else geometry.left + geometry.plot_width / 2
        y = geometry.bottom - geometry.ratio(value) * geometry.plot_height
        coords.append((x, y))

    path = " ".join(
        f'{"M" if index == 0 else "L"}{x:.1f},{y:.1f}'
        for index, (x, y) in enumerate(coords))
    parts.append(
        f'<path d="{path}" fill="none" stroke="{theme["primary"]}" '
        f'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    area = (f'{path} L{coords[-1][0]:.1f},{geometry.bottom:.1f} '
            f'L{coords[0][0]:.1f},{geometry.bottom:.1f} Z')
    parts.append(f'<path d="{area}" fill="{theme["primary"]}" opacity="0.08"/>')
    for index, (x, y) in enumerate(coords):
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" '
            f'fill="{theme["primary"]}"><title>{_escape(labels[index])}: '
            f'{_escape(fa_compact(values[index]))}</title></circle>')

    #: برچسب محور افقی — حداکثر ``MAX_X_LABELS`` برچسب، یکنواخت توزیع‌شده تا
    #: هیچ دو برچسبی روی هم نیفتد.
    stride = max(1, math.ceil(count / MAX_X_LABELS))
    for index in range(0, count, stride):
        x = coords[index][0]
        anchor = "middle"
        if index == 0:
            anchor = "start"
        elif index >= count - 1:
            anchor = "end"
        parts.append(
            f'<text x="{x:.1f}" y="{geometry.bottom + 18:.1f}" '
            f'text-anchor="{anchor}" font-size="11" fill="{theme["muted"]}">'
            f'{_escape(labels[index])}</text>')
    if unit:
        parts.append(
            f'<text x="{geometry.left:.1f}" y="{geometry.bottom + 34:.1f}" '
            f'text-anchor="start" font-size="10" fill="{theme["muted"]}">'
            f'بازه: {_escape(unit)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_donut(points: list[tuple[str, float, str, str]], theme: dict,
              *, title: str = "", center_label: str = "") -> str:
    """نمودار حلقه‌ای با راهنمای کنار — فقط وقتی ترکیب گروه‌ها معنا دارد.

    ``points`` چهارگانه‌های ``(برچسب, مقدار, متن مقدار, متن سهم)``.
    """
    total = sum(point[1] for point in points) or 1.0
    width, height = 720, 260
    radius, inner = 84, 50
    cx, cy = 150, height / 2 + 6
    parts = _svg_open(height, width, title)
    if title:
        parts.append(
            f'<text x="{width / 2:.1f}" y="20" text-anchor="middle" '
            f'font-size="13" font-weight="600" fill="{theme["ink"]}">'
            f'{_escape(title)}</text>')

    angle = -90.0
    for index, (label, value, _value_text, share_text) in enumerate(points):
        sweep = float(value) / total * 360
        if sweep <= 0:
            continue
        parts.append(_arc(cx, cy, radius, inner, angle, angle + sweep,
                          series_color(theme, index), f"{label}: {share_text}"))
        angle += sweep
    if center_label:
        parts.append(
            f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="15" '
            f'font-weight="700" fill="{theme["ink"]}">{_escape(center_label)}</text>')
        parts.append(
            f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" font-size="10" '
            f'fill="{theme["muted"]}">کل</text>')

    for index, (label, _value, value_text, share_text) in enumerate(points):
        y = 62 + index * 30
        parts.append(
            f'<rect x="{cx + radius + 34:.1f}" y="{y - 9:.1f}" width="12" '
            f'height="12" rx="3" fill="{series_color(theme, index)}"/>')
        parts.append(
            f'<text x="{cx + radius + 54:.1f}" y="{y + 1:.1f}" '
            f'text-anchor="start" font-size="12" fill="{theme["ink"]}">'
            f'{_escape(label)}</text>')
        parts.append(
            f'<text x="{width - 24:.1f}" y="{y + 1:.1f}" text-anchor="end" '
            f'font-size="11" fill="{theme["muted"]}">'
            f'{_escape(value_text)} · {_escape(share_text)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _arc(cx: float, cy: float, radius: float, inner: float,
         start: float, end: float, color: str, tooltip: str) -> str:
    """یک قطعهٔ حلقه — کمان بیرونی و درونی با هم."""
    large = 1 if (end - start) % 360 > 180 else 0
    outer_start = _polar(cx, cy, radius, start)
    outer_end = _polar(cx, cy, radius, end)
    inner_end = _polar(cx, cy, inner, end)
    inner_start = _polar(cx, cy, inner, start)
    path = (f'M{outer_start[0]:.2f},{outer_start[1]:.2f} '
            f'A{radius},{radius} 0 {large} 1 {outer_end[0]:.2f},{outer_end[1]:.2f} '
            f'L{inner_end[0]:.2f},{inner_end[1]:.2f} '
            f'A{inner},{inner} 0 {large} 0 {inner_start[0]:.2f},{inner_start[1]:.2f} Z')
    return (f'<path d="{path}" fill="{color}" stroke="white" stroke-width="1.5">'
            f'<title>{_escape(tooltip)}</title></path>')


def _polar(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return cx + radius * math.cos(radians), cy + radius * math.sin(radians)


def svg_histogram(points: list[tuple[str, float, str]], geometry: Geometry,
                  theme: dict, *, title: str = "") -> str:
    """هیستوگرام عمودی — میله‌های چسبیده برای نمایش توزیع."""
    parts = _svg_open(geometry.height, geometry.width, title)
    if title:
        parts.append(
            f'<text x="{geometry.width / 2:.1f}" y="20" text-anchor="middle" '
            f'font-size="13" font-weight="600" fill="{theme["ink"]}">'
            f'{_escape(title)}</text>')
    parts.extend(_grid_lines(geometry, theme,
                             [fa_compact(mark) for mark in geometry.value_ticks]))
    count = len(points)
    if not count:
        parts.append("</svg>")
        return "".join(parts)
    slot = geometry.plot_width / count
    for index, (label, value, value_text) in enumerate(points):
        height = geometry.ratio(value) * geometry.plot_height
        x = geometry.left + slot * index + 1.5
        y = geometry.bottom - height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(2.0, slot - 3):.1f}" '
            f'height="{max(1.0, height):.1f}" rx="2" '
            f'fill="{series_color(theme, index)}">'
            f'<title>{_escape(label)}: {_escape(value_text)}</title></rect>')
    #: برچسب محور افقی فقط روی بعضی میله‌ها می‌نشیند تا روی هم نیفتد.
    stride = max(1, math.ceil(count / MAX_X_LABELS))
    for index in range(0, count, stride):
        x = geometry.left + slot * index + slot / 2
        parts.append(
            f'<text x="{x:.1f}" y="{geometry.bottom + 16:.1f}" '
            f'text-anchor="middle" font-size="10" fill="{theme["muted"]}">'
            f'{_escape(points[index][0])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_scatter(xs: list[float], ys: list[float], geometry: Geometry,
                theme: dict, *, x_label: str = "", y_label: str = "",
                title: str = "") -> str:
    """نمودار پراکندگی برای همبستگی — نقطه‌ها هرگز زیر برچسب محور نمی‌روند."""
    parts = _svg_open(geometry.height, geometry.width, title)
    if title:
        parts.append(
            f'<text x="{geometry.width / 2:.1f}" y="20" text-anchor="middle" '
            f'font-size="13" font-weight="600" fill="{theme["ink"]}">'
            f'{_escape(title)}</text>')
    parts.extend(_grid_lines(geometry, theme,
                             [fa_compact(mark) for mark in geometry.value_ticks]))

    pairs = [(x, y) for x, y in zip(xs, ys)
             if x is not None and y is not None and x == x and y == y]
    if not pairs:
        parts.append("</svg>")
        return "".join(parts)
    x_low, x_high = min(x for x, _ in pairs), max(x for x, _ in pairs)
    x_span = (x_high - x_low) or 1.0
    for x, y in pairs:
        px = geometry.left + (x - x_low) / x_span * geometry.plot_width
        py = geometry.bottom - geometry.ratio(y) * geometry.plot_height
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" '
            f'fill="{theme["accent"]}" opacity="0.65"/>')
    #: برچسب محور افقی بیرون از ناحیهٔ رسم، با فاصلهٔ امن.
    parts.append(
        f'<text x="{geometry.right:.1f}" y="{geometry.height - 6:.1f}" '
        f'text-anchor="end" font-size="10" fill="{theme["muted"]}">'
        f'{_escape(x_label)} (محور افقی)</text>')
    parts.append(
        f'<text x="{geometry.left - 8:.1f}" y="{geometry.height - 6:.1f}" '
        f'text-anchor="end" font-size="10" fill="{theme["muted"]}">'
        f'{_escape(y_label)} (محور عمودی)</text>')
    parts.append("</svg>")
    return "".join(parts)


def empty_chart(reason: str, theme: dict, *, height: float = 150) -> str:
    """جایگزین نمودار وقتی داده کافی نیست — با دلیل، نه نمودار ساختگی."""
    parts = _svg_open(height, SVG_WIDTH, reason)
    parts.append(
        f'<rect x="1" y="1" width="{SVG_WIDTH - 2:g}" height="{height - 2:g}" '
        f'rx="10" fill="{theme["soft"]}" stroke="{theme["line"]}"/>')
    parts.append(
        f'<text x="{SVG_WIDTH / 2:g}" y="{height / 2 + 4:g}" '
        f'text-anchor="middle" font-size="12" fill="{theme["muted"]}">'
        f'{_escape(reason)}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------ رستر (PDF)
def _pillow_ready():
    """بارگذاری تنبل Pillow و شکل‌دهندهٔ فارسی.

    Pillow فقط برای PDF لازم است؛ اگر بالای فایل import شود، هر بار بالا آمدن
    سرویس (حتی برای صفحهٔ خانه) هزینهٔ آن را می‌دهد.
    """
    from PIL import Image, ImageDraw, ImageFont
    from arabic_reshaper import ArabicReshaper
    from bidi.algorithm import get_display

    from .config import font_path

    reshaper = ArabicReshaper()

    def shape(text: object) -> str:
        return get_display(reshaper.reshape(str(text)))

    def font(size: int, bold: bool = False):
        try:
            return ImageFont.truetype(font_path(bold), size)
        except OSError:
            return ImageFont.load_default()

    return Image, ImageDraw, font, shape


def png_bar(points: list[tuple[str, float, str]], theme: dict, *,
            title: str = "", width: int = 1240) -> bytes:
    """نمودار میله‌ای افقی برای PDF — با همان هندسهٔ SVG."""
    Image, ImageDraw, font, shape = _pillow_ready()
    scale = 2                                  #: چگالی دوبرابر برای PDF
    local = [(label, value, text) for label, value, text in points]
    geometry, centers = build_bar_geometry(
        [item[0] for item in local], [item[1] for item in local], width=width,
        row_height=SVG_BAR_HEIGHT * 1.4)
    height = int(geometry.height + 42)
    image = Image.new("RGB", (int(width), height), "white")
    draw = ImageDraw.Draw(image)
    body = font(20)
    small = font(18)
    heading = font(26, bold=True)

    if title:
        draw.text((width / 2, 26), shape(title), font=heading,
                  fill=theme["ink"], anchor="mm")
    shift = 44 if title else 12

    for mark in geometry.value_ticks:
        y = geometry.bottom - geometry.ratio(mark) * geometry.plot_height + shift
        draw.line([geometry.left, y, geometry.right, y], fill=theme["line"], width=1)
        draw.text((geometry.left - 10, y), shape(fa_compact(mark)), font=small,
                  fill=theme["muted"], anchor="rm")

    bar_height = (geometry.bottom - geometry.top) / max(1, len(local)) * 0.56
    for index, (label, value, value_text) in enumerate(local):
        center = centers[index] + shift
        length = max(3.0, geometry.ratio(value) * geometry.plot_width)
        draw.rounded_rectangle(
            [geometry.left, center - bar_height / 2,
             geometry.left + length, center + bar_height / 2],
            radius=5, fill=series_color(theme, index))
        draw.text((geometry.left + length + 8, center), shape(value_text),
                  font=small, fill=theme["muted"], anchor="lm")
        draw.text((geometry.right + 12, center), shape(label), font=body,
                  fill=theme["ink"], anchor="lm")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def png_line(labels: list[str], values: list[float], theme: dict, *,
             title: str = "", width: int = 1240, unit: str = "") -> bytes:
    """نمودار خطی برای PDF."""
    Image, ImageDraw, font, shape = _pillow_ready()
    geometry = build_line_geometry(labels, values, width=width,
                                   height=SVG_HEIGHT * 1.5)
    height = int(geometry.height + 30)
    image = Image.new("RGB", (int(width), height), "white")
    draw = ImageDraw.Draw(image)
    small = font(18)
    heading = font(26, bold=True)

    if title:
        draw.text((width / 2, 26), shape(title), font=heading,
                  fill=theme["ink"], anchor="mm")
    shift = 44 if title else 12

    for mark in geometry.value_ticks:
        y = geometry.bottom - geometry.ratio(mark) * geometry.plot_height + shift
        draw.line([geometry.left, y, geometry.right, y], fill=theme["line"], width=1)
        draw.text((geometry.left - 10, y), shape(fa_compact(mark)), font=small,
                  fill=theme["muted"], anchor="rm")

    count = len(values)
    step = geometry.plot_width / max(1, count - 1) if count > 1 else 0
    coords = []
    for index, value in enumerate(values):
        x = geometry.left + step * index if count > 1 else \
            geometry.left + geometry.plot_width / 2
        y = geometry.bottom - geometry.ratio(value) * geometry.plot_height + shift
        coords.append((x, y))
    if len(coords) > 1:
        draw.line(coords, fill=theme["primary"], width=4, joint="curve")
    for x, y in coords:
        draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=theme["primary"])

    stride = max(1, math.ceil(count / MAX_X_LABELS))
    for index in range(0, count, stride):
        draw.text((coords[index][0], geometry.bottom + shift + 20),
                  shape(labels[index]), font=small, fill=theme["muted"],
                  anchor="mm")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def png_donut(points: list[tuple[str, float, str, str]], theme: dict, *,
              title: str = "", width: int = 1240) -> bytes:
    """نمودار حلقه‌ای برای PDF."""
    Image, ImageDraw, font, shape = _pillow_ready()
    height = 460
    image = Image.new("RGB", (int(width), height), "white")
    draw = ImageDraw.Draw(image)
    heading = font(26, bold=True)
    body = font(20)
    small = font(18)

    if title:
        draw.text((width / 2, 26), shape(title), font=heading, fill=theme["ink"],
                  anchor="mm")
    total = sum(point[1] for point in points) or 1.0
    radius, inner = 130, 78
    cx, cy = 260, height / 2 + 16
    angle = -90.0
    for index, (_label, value, _value_text, _share) in enumerate(points):
        sweep = float(value) / total * 360
        box = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.pieslice(box, angle, angle + sweep, fill=series_color(theme, index),
                      outline="white", width=3)
        angle += sweep
    draw.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill="white")

    for index, (label, _value, value_text, share_text) in enumerate(points):
        y = 120 + index * 44
        draw.rounded_rectangle([cx + radius + 46, y, cx + radius + 66, y + 20],
                               radius=5, fill=series_color(theme, index))
        draw.text((cx + radius + 78, y + 10), shape(label), font=body,
                  fill=theme["ink"], anchor="lm")
        draw.text((width - 40, y + 10), shape(f"{value_text} · {share_text}"),
                  font=small, fill=theme["muted"], anchor="rm")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def png_histogram(points: list[tuple[str, float, str]], theme: dict, *,
                  title: str = "", width: int = 1240) -> bytes:
    """هیستوگرام برای PDF."""
    Image, ImageDraw, font, shape = _pillow_ready()
    geometry = build_geometry([item[0] for item in points],
                              [item[1] for item in points], width=width,
                              height=SVG_HEIGHT * 1.5)
    height = int(geometry.height + 30)
    image = Image.new("RGB", (int(width), height), "white")
    draw = ImageDraw.Draw(image)
    small = font(18)
    heading = font(26, bold=True)
    if title:
        draw.text((width / 2, 26), shape(title), font=heading, fill=theme["ink"],
                  anchor="mm")
    shift = 44 if title else 12
    for mark in geometry.value_ticks:
        y = geometry.bottom - geometry.ratio(mark) * geometry.plot_height + shift
        draw.line([geometry.left, y, geometry.right, y], fill=theme["line"], width=1)
        draw.text((geometry.left - 10, y), shape(fa_compact(mark)), font=small,
                  fill=theme["muted"], anchor="rm")
    count = len(points)
    slot = geometry.plot_width / max(1, count)
    for index, (_label, value, _text) in enumerate(points):
        bar = geometry.ratio(value) * geometry.plot_height
        x = geometry.left + slot * index + 2
        draw.rectangle([x, geometry.bottom + shift - bar, x + slot - 4,
                        geometry.bottom + shift], fill=series_color(theme, index))
    stride = max(1, math.ceil(count / MAX_X_LABELS))
    for index in range(0, count, stride):
        draw.text((geometry.left + slot * index + slot / 2,
                   geometry.bottom + shift + 20), shape(points[index][0]),
                  font=small, fill=theme["muted"], anchor="mm")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def png_scatter(xs: list[float], ys: list[float], theme: dict, *,
                title: str = "", x_label: str = "", y_label: str = "",
                width: int = 1240) -> bytes:
    """نمودار پراکندگی برای PDF."""
    Image, ImageDraw, font, shape = _pillow_ready()
    geometry = build_geometry([], list(ys) or [0.0], width=width,
                              height=SVG_HEIGHT * 1.4)
    height = int(geometry.height + 30)
    image = Image.new("RGB", (int(width), height), "white")
    draw = ImageDraw.Draw(image)
    small = font(18)
    heading = font(26, bold=True)
    if title:
        draw.text((width / 2, 26), shape(title), font=heading, fill=theme["ink"],
                  anchor="mm")
    shift = 44 if title else 12
    for mark in geometry.value_ticks:
        y = geometry.bottom - geometry.ratio(mark) * geometry.plot_height + shift
        draw.line([geometry.left, y, geometry.right, y], fill=theme["line"], width=1)
        draw.text((geometry.left - 10, y), shape(fa_compact(mark)), font=small,
                  fill=theme["muted"], anchor="rm")
    pairs = [(x, y) for x, y in zip(xs, ys) if x == x and y == y]
    if pairs:
        low, high = min(x for x, _ in pairs), max(x for x, _ in pairs)
        span = (high - low) or 1.0
        for x, y in pairs:
            px = geometry.left + (x - low) / span * geometry.plot_width
            py = geometry.bottom - geometry.ratio(y) * geometry.plot_height + shift
            draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=theme["accent"])
    draw.text((geometry.right, geometry.height + shift - 4),
              shape(f"{x_label} (محور افقی)"), font=small, fill=theme["muted"],
              anchor="rm")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _png_bytes(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
