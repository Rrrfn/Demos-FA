# -*- coding: utf-8 -*-
"""خروجی PDF — گزارش چندصفحه‌ای با متن فارسی صحیح.

متن فارسی در PDF دو مرحله لازم دارد که هر دو اینجا انجام می‌شود:

۱) **شکل‌دهی حروف** (``arabic_reshaper``): حرف فارسی بسته به جایگاهش در واژه
   شکل عوض می‌کند. بدون این مرحله، «س» و «ل» و «ا» جدا از هم و ناخوانا
   چاپ می‌شوند.

۲) **ترتیب بصری** (``bidi``): موتور PDF از چپ به راست می‌نویسد، ولی فارسی
   راست‌به‌چپ است. تبدیل ترتیب منطقی به بصری کار ``get_display`` است.

هیچ رشته‌ای بدون این دو مرحله روی صفحه نمی‌رود؛ به همین دلیل همهٔ متن‌ها از
تابع ``text`` رد می‌شوند و نه مستقیم از ``cell``.

فونت وزیرمتن همراه پروژه است (``fonts/``) تا خروجی به فونت نصب‌شدهٔ سرور
وابسته نباشد — سرور رایگان فونت فارسی ندارد.
"""
from __future__ import annotations

import io
import os

from .analytics import Analysis
from .charts import (png_bar, png_donut, png_histogram, png_line, png_scatter)
from .config import OUTPUT_BASENAMES, font_path
from .report import Block, Report


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


class PdfReport:
    """سازندهٔ PDF گزارش — با زبان مشترک واحدهای میلی‌متری fpdf."""

    def __init__(self, report: Report) -> None:
        self.report = report
        self.theme = report.theme
        self.primary = _rgb(self.theme["primary"])
        self.accent = _rgb(self.theme["accent"])
        self.ink = _rgb(self.theme["ink"])
        self.muted = _rgb(self.theme["muted"])
        self.line = _rgb(self.theme["line"])
        self.soft = _rgb(self.theme["soft"])
        self._reshaper = None
        self._shaper = None
        self.pdf = None
        self.page_width = 210.0
        self.margin = 16.0
        self._charts: dict[str, bytes] = {}

    # ------------------------------------------------------------ شکل‌دهی
    def _ensure_shaper(self):
        if self._shaper is None:
            from arabic_reshaper import ArabicReshaper
            from bidi.algorithm import get_display

            self._reshaper = ArabicReshaper()
            self._shaper = (self._reshaper, get_display)
        return self._shaper

    def text(self, value: object) -> str:
        """رشتهٔ آمادهٔ چاپ — شکل‌دهی و ترتیب بصری."""
        raw = "" if value is None else str(value)
        if not raw:
            return ""
        reshaper, get_display = self._ensure_shaper()
        #: خطوط جداگانه شکل می‌گیرند تا الگوریتم دوجهته هر خط را جدا ببیند.
        return "\n".join(get_display(reshaper.reshape(line)) for line in raw.split("\n"))

    # ------------------------------------------------------------ ساخت
    def build(self, *, analysis: Analysis,
              frame=None) -> bytes:
        """ساخت PDF کامل و برگرداندن بایت‌های آن."""
        from fpdf import FPDF

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.set_margins(self.margin, 14, self.margin)
        self.pdf = pdf
        self.page_width = pdf.w
        self._charts = self._render_charts(analysis, frame)

        self._register_fonts()
        self._cover()
        self._content(analysis)
        payload = pdf.output()
        return bytes(payload)

    def _register_fonts(self) -> None:
        pdf = self.pdf
        regular = font_path(False)
        bold = font_path(True)
        if not os.path.isfile(regular):
            raise RuntimeError("فونت وزیرمتن پیدا نشد؛ خروجی PDF بدون آن "
                               "قابل ساخت نیست.")
        pdf.add_font("Vazir", "", regular)
        pdf.add_font("Vazir", "B", bold if os.path.isfile(bold) else regular)
        pdf.set_font("Vazir", "", 11)

    # ------------------------------------------------------------ صفحه‌آرایی
    def _set(self, size: int = 11, bold: bool = False,
             color: tuple[int, int, int] | None = None) -> None:
        self.pdf.set_font("Vazir", "B" if bold else "", size)
        self.pdf.set_text_color(*(color or self.ink))

    def _width(self) -> float:
        return self.page_width - 2 * self.margin

    def _heading(self, title: str, *, size: int = 15) -> None:
        pdf = self.pdf
        if pdf.get_y() > pdf.h - 46:
            pdf.add_page()
        self._set(size, bold=True, color=self.primary)
        pdf.multi_cell(self._width(), 9, self.text(title), align="R")
        y = pdf.get_y() + 1.0
        pdf.set_draw_color(*self.accent)
        pdf.set_line_width(0.6)
        pdf.line(self.page_width - self.margin, y,
                 self.page_width - self.margin - 26, y)
        pdf.ln(3.5)

    def _paragraph(self, body: str, *, size: int = 10.5,
                   color: tuple[int, int, int] | None = None) -> None:
        self._set(size, color=color or self.ink)
        self.pdf.multi_cell(self._width(), 6.2, self.text(body), align="R")
        self.pdf.ln(1.4)

    def _bullets(self, items: list[str]) -> None:
        self._set(10, color=self.ink)
        for item in items:
            self.pdf.set_x(self.margin + 4)
            self.pdf.multi_cell(self._width() - 4, 5.8, self.text("• " + str(item)),
                                align="R")
        self.pdf.ln(1.6)

    def _callout(self, title: str, body: str, severity: str = "info") -> None:
        pdf = self.pdf
        if pdf.get_y() > pdf.h - 52:
            pdf.add_page()
        color = {"critical": (198, 74, 74), "warning": (196, 140, 48),
                 "info": self.primary}.get(severity, self.primary)
        top = pdf.get_y()
        pdf.set_fill_color(*self.soft)
        self._set(10.5, bold=True, color=color)
        height = 8 + 6.2 * max(1, self._wrapped_lines(body, 10))
        pdf.rect(self.margin, top, self._width(), height + 8, style="F")
        pdf.set_xy(self.margin + 3, top + 2)
        pdf.cell(self._width() - 6, 6, self.text(title), align="R")
        pdf.set_xy(self.margin + 3, top + 9)
        self._set(10, color=self.ink)
        pdf.multi_cell(self._width() - 6, 6, self.text(body), align="R")
        pdf.set_y(top + height + 11)

    def _wrapped_lines(self, body: str, size: int) -> int:
        """تخمین شمار خطوط یک پاراگراف — برای کشیدن کادر یادداشت."""
        width = self._width() - 6
        average = size * 0.55
        per_line = max(1, int(width / average))
        return max(1, int(len(str(body)) / per_line) + 1)

    def _kpi_cards(self, items: list[dict]) -> None:
        """کارت‌های شاخص در شبکهٔ دوستونی."""
        pdf = self.pdf
        gap = 5.0
        card_width = (self._width() - gap) / 2
        card_height = 24.0
        index = 0
        while index < len(items):
            if pdf.get_y() + card_height > pdf.h - 24:
                pdf.add_page()
            top = pdf.get_y()
            pair = items[index:index + 2]
            for offset, item in enumerate(pair):
                left = self.page_width - self.margin - card_width * (offset + 1) \
                    - gap * offset
                pdf.set_fill_color(*self.soft)
                pdf.rect(left, top, card_width, card_height, style="F")
                pdf.set_draw_color(*self.line)
                pdf.rect(left, top, card_width, card_height)
                self._set(11, color=self.muted)
                pdf.set_xy(left + 3, top + 2.5)
                pdf.cell(card_width - 6, 5, self.text(item.get("label", "")),
                         align="R")
                self._set(15, bold=True, color=self.ink)
                pdf.set_xy(left + 3, top + 8.5)
                pdf.cell(card_width - 6, 8, self.text(item.get("value", "")),
                         align="R")
                change = item.get("change") or ""
                direction = item.get("direction") or ""
                hint = item.get("hint", "")
                if change:
                    #: فونت وزیرمتن نویسهٔ مثلث ▲▼ را ندارد و متن جایگزین
                    #: (豆腐) چاپ می‌شد؛ واژهٔ فارسی جای آن می‌نشیند.
                    arrow = "افزایش" if direction == "up" else "کاهش"
                    hint = f"{arrow} {change} — {hint}"
                self._set(9, color=self.muted)
                pdf.set_xy(left + 3, top + 17.5)
                pdf.cell(card_width - 6, 5, self.text(hint), align="R")
            pdf.set_y(top + card_height + gap)
            index += 2
        pdf.ln(2)

    def _table(self, columns: list[str], rows: list[list],
               caption: str = "") -> None:
        pdf = self.pdf
        if caption:
            self._set(9.5, color=self.muted)
            pdf.multi_cell(self._width(), 5.4, self.text(caption), align="R")
            pdf.ln(1.0)
        headers = [str(item) for item in columns]
        count = max(1, len(headers))
        #: عرض ستون بر اساس بلندترین محتوا، با وزن مساوی به‌عنوان پایه.
        widths = []
        for index in range(count):
            longest = max([len(headers[index])] +
                          [len(str(row[index])) for row in rows
                           if len(row) > index and row[index] is not None] or [4])
            widths.append(longest)
        total = sum(widths) or 1
        available = self._width()
        column_widths = [max(14.0, available * weight / total) for weight in widths]
        scale = available / sum(column_widths)
        column_widths = [value * scale for value in column_widths]

        def _row(values: list, bold: bool, background: bool) -> None:
            pdf.set_x(self.margin)
            line_height = 6.4
            top = pdf.get_y()
            if top + line_height > pdf.h - 18:
                pdf.add_page()
                top = pdf.get_y()
            if background:
                pdf.set_fill_color(*self.soft)
                pdf.rect(self.margin, top, available, line_height, style="F")
            pdf.set_draw_color(*self.line)
            pdf.set_line_width(0.2)
            left = self.page_width - self.margin
            for index, value in enumerate(values):
                width = column_widths[index] if index < len(column_widths) \
                    else column_widths[-1]
                left -= width
                self._set(9, bold=bold)
                pdf.set_xy(left, top)
                pdf.cell(width, line_height,
                         self.text(str(value)[:60]), align="R", border=0)
                pdf.rect(left, top, width, line_height)
            pdf.set_y(top + line_height)

        _row(headers, True, False)
        for offset, values in enumerate(rows):
            _row(list(values), False, offset % 2 == 1)
        pdf.ln(3)

    def _image(self, payload: bytes, width_ratio: float = 1.0) -> None:
        pdf = self.pdf
        stream = io.BytesIO(payload)
        width = self._width() * width_ratio
        #: نسبت تصویر از خودش خوانده می‌شود تا کشیدگی نداشته باشد.
        try:
            from PIL import Image

            with Image.open(io.BytesIO(payload)) as probe:
                ratio = probe.height / max(1, probe.width)
        except Exception:                                   # noqa: BLE001
            ratio = 0.42
        height = width * ratio
        if pdf.get_y() + height > pdf.h - 20:
            pdf.add_page()
        pdf.image(stream, x=self.margin, y=pdf.get_y(), w=width)
        pdf.set_y(pdf.get_y() + height + 4)

    # ------------------------------------------------------------ نمودارها
    def _render_charts(self, analysis: Analysis, frame) -> dict[str, bytes]:
        """ساخت تصویر نمودارها — همان داده‌ای که SVG وب از آن ساخته شده."""
        charts: dict[str, bytes] = {}
        for series in analysis.series:
            if not series.points:
                continue
            labels = [point.label for point in series.points]
            values = [point.value for point in series.points]
            try:
                if series.key == "trend":
                    charts[series.key] = png_line(labels, values, self.theme,
                                                  title=series.title,
                                                  unit=series.unit)
                elif series.key == "breakdown":
                    points = [(point.label, point.value, _compact(point.value))
                              for point in series.points]
                    charts[series.key] = png_bar(points, self.theme,
                                                 title=series.title)
                elif series.key == "distribution":
                    points = [(point.label, point.value, _compact(point.value))
                              for point in series.points]
                    charts[series.key] = png_histogram(points, self.theme,
                                                       title=series.title)
            except Exception:                                # noqa: BLE001
                #: اگر یک نمودار ساخته نشد، گزارش باید همچنان صادر شود.
                continue
        if analysis.breakdowns and analysis.breakdowns[0].rows:
            rows = analysis.breakdowns[0].rows[:6]
            points = [(row["label"], row["value"], row["value_text"],
                       row["share_text"]) for row in rows]
            try:
                charts["donut"] = png_donut(points, self.theme,
                                            title="سهم گروه‌ها")
            except Exception:                                # noqa: BLE001
                pass
        if analysis.correlation.get("columns") and frame is not None:
            names = analysis.correlation["columns"]
            if len(names) >= 2:
                from .analytics import _numeric

                try:
                    x_values = _numeric(frame, names[0]).tolist()
                    y_values = _numeric(frame, names[1]).tolist()
                    charts["scatter"] = png_scatter(
                        x_values, y_values, self.theme,
                        title=f"{names[1]} در برابر {names[0]}",
                        x_label=names[0], y_label=names[1])
                except Exception:                            # noqa: BLE001
                    pass
        return charts

    # ------------------------------------------------------------ صفحه‌ها
    def _cover(self) -> None:
        pdf = self.pdf
        pdf.add_page()
        pdf.set_fill_color(*self.primary)
        pdf.rect(0, 0, pdf.w, 62, style="F")
        pdf.set_fill_color(*self.accent)
        pdf.rect(0, 62, pdf.w, 2.4, style="F")

        self._set(26, bold=True, color=(255, 255, 255))
        pdf.set_xy(self.margin, 20)
        pdf.multi_cell(self._width(), 12, self.text(self.report.title), align="R")
        self._set(12, color=(232, 240, 238))
        pdf.set_x(self.margin)
        pdf.multi_cell(self._width(), 7, self.text(self.report.subtitle), align="R")

        pdf.set_y(78)
        self._set(12, bold=True, color=self.primary)
        pdf.cell(self._width(), 8, self.text("مشخصات پردازش"), align="R")
        pdf.ln(9)

        for label, value in self.report.meta_lines:
            top = pdf.get_y()
            pdf.set_fill_color(*self.soft)
            pdf.rect(self.margin, top, self._width(), 8, style="F")
            self._set(10, bold=True, color=self.muted)
            pdf.set_xy(self.margin + 2, top)
            pdf.cell(40, 8, self.text(label), align="R")
            self._set(10, color=self.ink)
            pdf.set_xy(self.margin + 44, top)
            pdf.cell(self._width() - 46, 8, self.text(value), align="R")
            pdf.set_y(top + 9.4)

        pdf.set_y(pdf.h - 34)
        pdf.set_draw_color(*self.line)
        pdf.set_line_width(0.3)
        pdf.line(self.margin, pdf.h - 30, pdf.w - self.margin, pdf.h - 30)
        self._set(8.5, color=self.muted)
        pdf.set_xy(self.margin, pdf.h - 27)
        pdf.multi_cell(
            self._width(), 4.6,
            self.text("این گزارش به‌صورت خودکار از فایل بارگذاری‌شده ساخته شده "
                      "است. همهٔ اعداد از همان جدول محاسبه شده‌اند و هیچ مقدار "
                      "نمونه‌ای یا تخمینی در آن درج نشده است."), align="R")
        pdf.add_page()

    def _content(self, analysis: Analysis) -> None:
        for section in self.report.sections:
            if section.key == "appendix":
                continue                 #: پیوست در صفحهٔ جدا آمده است
            if section.new_page:
                self.pdf.add_page()
            self._heading(section.title)
            for block in section.blocks:
                self._block(block)
            self.pdf.ln(3)

        self._methodology(analysis)

    def _block(self, block: Block) -> None:
        kind = block.kind
        data = block.data
        if kind == "paragraph":
            self._paragraph(data.get("text", ""))
        elif kind == "list":
            if data.get("title"):
                self._paragraph(data["title"], size=11)
            self._bullets(data.get("entries", []))
        elif kind == "notes":
            self._paragraph(data.get("title", "یادداشت"), size=11)
            self._bullets(data.get("entries", []))
        elif kind == "kpis":
            self._kpi_cards(data.get("entries", []))
        elif kind == "callout":
            self._callout(data.get("title", ""), data.get("body", ""),
                          data.get("severity", "info"))
        elif kind == "callouts":
            for item in data.get("entries", []):
                self._callout(item.get("title", ""), item.get("body", ""),
                              item.get("severity", "info"))
        elif kind == "table":
            self._table(data.get("columns", []), data.get("rows", []),
                        data.get("caption", ""))
        elif kind == "chart":
            payload = self._charts.get(data.get("key", ""))
            if data.get("caption"):
                self._paragraph(data["caption"], size=10)
            if payload:
                self._image(payload)
            else:
                self._paragraph("نمودار این بخش ساخته نشد.", size=10,
                                color=self.muted)

    def _methodology(self, analysis: Analysis) -> None:
        """صفحهٔ روش کار — شفافیت، نه تزئین."""
        pdf = self.pdf
        pdf.add_page()
        self._heading("روش کار و محدودیت‌ها")

        self._paragraph(
            "این بخش توضیح می‌دهد هر عدد گزارش از کجا آمده و کجا نمی‌توان به "
            "آن تکیه کرد. هدف این است که خواننده بتواند خودش قضاوت کند، نه "
            "این‌که به خروجی اعتماد کورکورانه کند.")

        self._set(11, bold=True, color=self.primary)
        pdf.cell(self._width(), 7, self.text("مراحل پردازش"), align="R")
        pdf.ln(8)
        self._bullets([
            "کیفیت داده: چهار زیرامتیاز وزن‌دار — کامل‌بودن ۳۵٪، اعتبار ۲۵٪، "
            "یکتایی ۲۰٪ و یکدستی ۲۰٪.",
            "پاک‌سازی: تنها اصلاح‌هایی اعمال شد که در صفحهٔ «پاک‌سازی» "
            "مشخص شده‌اند؛ هر اصلاح با شمار دقیقش ثبت شده است.",
            "شناسایی نوع ستون: نوع هر ستون روی نمونه‌ای از داده با نسبت "
            "پذیرش ۸۵٪ تعیین می‌شود.",
            "ناهنجاری: دو روش IQR (۱٫۵ برابر دامنهٔ میان‌چارکی) و Z-score "
            "(آستانهٔ ۳ انحراف معیار) با هم به‌کار رفته‌اند.",
            "رشد دوره‌ها: مقایسهٔ جمع نیمهٔ اول و دوم بازهٔ تاریخی، با مرزِ "
            "میانهٔ زمانی بازه و نه میانهٔ شمار ردیف؛ نه مقایسهٔ دو سطر آخر.",
        ])

        self._set(11, bold=True, color=self.primary)
        pdf.cell(self._width(), 7, self.text("محدودیت‌های صریح"), align="R")
        pdf.ln(8)
        limitations = [
            "این گزارش هیچ عددی را *حدس نمی‌زند*: اگر ستون مناسبی نباشد، بخش "
            "مربوطه خالی می‌ماند و دلیلش گفته می‌شود.",
            "همبستگی، علت نیست. ضریب بالا یعنی دو ستون با هم حرکت می‌کنند، نه "
            "این‌که یکی دیگری را باعث می‌شود.",
            "مقدارهای مشکوک و ناهنجار فقط علامت‌گذاری شده‌اند و از جدول حذف "
            "نشده‌اند؛ تصمیم دربارهٔ آن‌ها با کاربر است.",
            "اگر فایل به سقف تعداد سطر رسیده باشد، در فراداده و در همین گزارش "
            "اعلام شده است.",
            "گزارش بر پایهٔ همان فایلی است که بارگذاری شده؛ نه اعتبارسنجی "
            "مستقل و نه مقایسه با منبع بیرونی روی آن انجام نشده است.",
        ]
        self._bullets(limitations)
        if analysis.notes:
            self._paragraph("یادداشت‌های همین تحلیل:", size=10.5)
            self._bullets(analysis.notes)

        #: ------------------------------------------------------ پیوست
        pdf.add_page()
        appendix = self.report.section("appendix")
        if appendix:
            self._heading(appendix.title)
            for block in appendix.blocks:
                self._block(block)


# ------------------------------------------------------------------ کمکی
def _compact(value: object) -> str:
    from .labels import fa_compact

    return fa_compact(value)


def build_pdf(report: Report, *, analysis: Analysis, frame=None) -> bytes:
    """ساخت بایت‌های PDF گزارش."""
    return PdfReport(report).build(analysis=analysis, frame=frame)


def filename() -> str:
    """نام فایل خروجی PDF."""
    return f"{OUTPUT_BASENAMES['pdf']}.pdf"
