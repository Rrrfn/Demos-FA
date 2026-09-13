# -*- coding: utf-8 -*-
"""سازندهٔ ساختار گزارش — یک مدل، دو خروجی.

گزارش یک بار ساخته می‌شود و دو جا مصرف می‌شود: پیش‌نمایش HTML در سایت و PDF
دانلودی. اگر هر خروجی محتوای خودش را بسازد، دیر یا زود این دو از هم جدا
می‌شوند و کاربر در سایت چیزی می‌بیند که در PDF نیست. پس ساختار اینجاست و
رندرکننده‌ها فقط *می‌کشند*.

بلوک‌ها عمداً ساده‌اند — پاراگراف، کارت، جدول، نمودار، یادداشت. هر بلوک دادهٔ
خودش را کامل دارد و برای نمایش به هیچ محاسبهٔ دیگری نیاز ندارد.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .analytics import Analysis
from .cleaning import CleanResult
from .config import (QUALITY_METHOD, QUALITY_WEIGHTS, THEMES,
                     theme as theme_of)
from .labels import fa_bytes, fa_compact, fa_datetime, fa_number, fa_percent
from .profile import Profile

#: بخش‌های استاندارد گزارش، به ترتیب.
SECTION_SUMMARY = "summary"
SECTION_QUALITY = "quality"
SECTION_KPIS = "kpis"
SECTION_CHARTS = "charts"
SECTION_INSIGHTS = "insights"
SECTION_DETAIL = "detail"
SECTION_APPENDIX = "appendix"


@dataclass
class Block:
    """یک بلوک محتوایی در گزارش."""

    kind: str
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, **self.data}


@dataclass
class Section:
    """یک بخش گزارش."""

    key: str
    title: str
    blocks: list[Block] = field(default_factory=list)
    #: آیا این بخش در PDF صفحهٔ تازه می‌گیرد؟
    new_page: bool = False

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "new_page": self.new_page,
                "blocks": [block.as_dict() for block in self.blocks]}


@dataclass
class Report:
    """گزارش کامل — آمادهٔ رندر."""

    title: str
    subtitle: str
    theme_name: str
    meta_lines: list[tuple[str, str]] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)

    @property
    def theme(self) -> dict:
        return theme_of(self.theme_name)

    def section(self, key: str) -> Section | None:
        for item in self.sections:
            if item.key == key:
                return item
        return None

    def as_dict(self) -> dict:
        return {
            "title": self.title, "subtitle": self.subtitle,
            "theme": self.theme_name,
            "theme_label": self.theme.get("label", ""),
            "meta_lines": [{"label": label, "value": value}
                           for label, value in self.meta_lines],
            "sections": [section.as_dict() for section in self.sections],
        }


# ------------------------------------------------------------------ سازنده
def build_report(*, title: str, subtitle: str, meta: dict, profile: Profile,
                 analysis: Analysis, clean: CleanResult | None,
                 theme_name: str, svg_charts: dict[str, str] | None = None) -> Report:
    """ساخت گزارش از خروجی همهٔ لایه‌ها.

    ``svg_charts`` نمودارهای آمادهٔ رندرشده‌اند؛ ساختشان کار لایهٔ وب است تا
    این ماژول به کتابخانهٔ نمودار وابسته نشود.
    """
    charts = svg_charts or {}
    report = Report(title=title, subtitle=subtitle, theme_name=theme_name)
    report.meta_lines = _meta_lines(meta, profile)

    report.sections.append(_summary_section(profile, analysis, clean))
    report.sections.append(_quality_section(profile))
    report.sections.append(_kpi_section(analysis))
    report.sections.append(_chart_section(analysis, charts))
    report.sections.append(_insight_section(analysis))
    report.sections.append(_detail_section(profile, analysis, clean))
    report.sections.append(_appendix_section(profile))
    return report


def _meta_lines(meta: dict, profile: Profile) -> list[tuple[str, str]]:
    """فهرست «برچسب: مقدار» سرصفحهٔ گزارش."""
    lines = [
        ("نام فایل", meta.get("display_name", "—")),
        ("تاریخ پردازش", fa_datetime(meta.get("processed_at", ""))),
        ("حجم فایل", fa_bytes(meta.get("size_bytes", 0))),
        ("ردیف × ستون", f"{fa_number(profile.rows)} × {fa_number(profile.columns)}"),
    ]
    if meta.get("sheet"):
        lines.append(("شیت پردازش‌شده", str(meta["sheet"])))
    if meta.get("encoding"):
        lines.append(("کدگذاری", str(meta["encoding"])))
    theme_names = meta.get("theme_label")
    if theme_names:
        lines.append(("تم گزارش", str(theme_names)))
    return lines


def _summary_section(profile: Profile, analysis: Analysis,
                     clean: CleanResult | None) -> Section:
    """خلاصهٔ مدیریتی — چند جمله، همه از داده."""
    blocks: list[Block] = []
    sentences: list[str] = []

    sentences.append(
        f"این گزارش از جدولی با {fa_number(profile.rows)} سطر و "
        f"{fa_number(profile.columns)} ستون ساخته شده است.")

    if clean and clean.rows_removed:
        sentences.append(
            f"در مرحلهٔ پاک‌سازی {fa_number(clean.rows_removed)} سطر "
            f"({fa_percent(clean.rows_removed / max(1, clean.rows_before))}) "
            "حذف شد که بیشتر آن ردیف تکراری بود.")

    if analysis.primary_metric:
        total_kpi = next((kpi for kpi in analysis.kpis if kpi.key == "total"), None)
        if total_kpi:
            sentence = f"جمع «{analysis.primary_metric}» برابر {total_kpi.value} است"
            if total_kpi.change:
                sentence += (f" و نسبت به نیمهٔ نخست بازه {total_kpi.change} "
                             f"{'افزایش' if total_kpi.direction == 'up' else 'کاهش'}"
                             " داشته است")
            sentences.append(sentence + ".")
    else:
        sentences.append(
            "در این جدول ستون عددی مناسبی برای جمع‌بندی پیدا نشد، پس کارت‌های "
            "شاخص ساخته نشدند.")

    if analysis.primary_dimension and analysis.breakdowns:
        main = analysis.breakdowns[0]
        if main.rows:
            top = main.rows[0]
            sentences.append(
                f"بزرگ‌ترین گروه در «{analysis.primary_dimension}» گروه "
                f"«{top['label']}» با {top['share_text']} سهم است.")

    quality = profile.quality.get("score")
    if quality is not None:
        sentences.append(
            f"امتیاز کیفیت داده {fa_number(quality, decimals=1)} از ۱۰۰ با "
            f"برچسب «{profile.quality.get('label', '')}» است.")

    blocks.append(Block("paragraph", {"text": " ".join(sentences)}))
    if analysis.notes:
        blocks.append(Block("notes", {"title": "محدودیت‌های این تحلیل",
                                      "entries": list(analysis.notes)}))
    return Section(SECTION_SUMMARY, "خلاصهٔ مدیریتی", blocks)


def _quality_section(profile: Profile) -> Section:
    """بخش کیفیت داده — چهار زیرامتیاز، وزن‌ها و روش کار."""
    quality = profile.quality
    parts = quality.get("parts", {})
    #: شرح و وزن هر زیرامتیاز از یک منبع می‌آید، نه از دو جای جدا — تناقض
    #: بین عدد و وزنش در گزارش، اعتماد را از بین می‌برد.
    descriptions = {
        "completeness": ("کامل‌بودن", f"{fa_number(profile.missing)} سلول خالی "
                                        f"از {fa_number(profile.cells)} سلول"),
        "validity": ("اعتبار", "نسبت سلول‌هایی که با نوع تشخیص‌داده‌شدهٔ ستون "
                               "می‌خوانند"),
        "uniqueness": ("یکتایی", f"{fa_number(profile.duplicates)} سطر کاملاً تکراری"),
        "consistency": ("یکدستی", "یکسان بودن قالب نمایش مقدارها در هر ستون"),
    }
    rows = []
    for key, weight in QUALITY_WEIGHTS.items():
        label, description = descriptions.get(key, (key, ""))
        rows.append([label, fa_percent(parts.get(key, 0) / 100), description,
                     fa_percent(weight)])

    blocks = [
        Block("kpis", {"entries": [
            {"label": "امتیاز کیفیت داده",
             "value": fa_number(quality.get("score", 0), decimals=1),
             "hint": f"از ۱۰۰ — {quality.get('label', '')}", "direction": "",
             "change": ""},
            {"label": "سطر تکراری",
             "value": fa_number(profile.duplicates),
             "hint": "پس از پاک‌سازی", "direction": "", "change": ""},
            {"label": "سلول خالی",
             "value": fa_number(profile.missing),
             "hint": f"از {fa_number(profile.cells)} سلول", "direction": "",
             "change": ""},
        ]}),
        Block("table", {
            "columns": ["زیرامتیاز", "مقدار", "توضیح", "وزن"],
            "rows": rows,
            "caption": "چهار زیرامتیاز امتیاز کیفیت",
        }),
        Block("callout", {"severity": "info", "title": "روش محاسبه",
                          "body": QUALITY_METHOD}),
    ]
    if profile.notes:
        blocks.append(Block("list", {"title": "یادداشت‌های کیفیت داده",
                                     "entries": list(profile.notes)}))
    return Section(SECTION_QUALITY, "کیفیت داده", blocks)


def _kpi_section(analysis: Analysis) -> Section:
    """بخش شاخص‌های کلیدی."""
    blocks: list[Block] = []
    if analysis.kpis:
        blocks.append(Block("kpis", {"entries": [
            {"label": kpi.label, "value": kpi.value, "hint": kpi.hint,
             "direction": kpi.direction, "change": kpi.change}
            for kpi in analysis.kpis
        ]}))
    else:
        blocks.append(Block("callout", {
            "severity": "warning", "title": "شاخصی ساخته نشد",
            "body": "ستون عددی مناسبی برای ساخت شاخص در این جدول پیدا نشد. "
                    "این یعنی داده کم است یا نوع ستون‌های عددی درست تشخیص داده "
                    "نشده — نه این‌که شاخص صفر است."}))
    return Section(SECTION_KPIS, "شاخص‌های کلیدی", blocks)


def _chart_section(analysis: Analysis, charts: dict[str, str]) -> Section:
    """بخش نمودارها — فقط نمودارهایی که داده دارند.

    نمودارهای حلقه‌ای و پراکندگی عضو ``analysis.series`` نیستند (یکی از تفکیک
    گروه‌ها و دیگری از همبستگی ساخته می‌شود) ولی نمودارهای واقعی‌اند؛ اگر اینجا
    اضافه نشوند، در گزارش و PDF غایب می‌مانند در حالی که در صفحهٔ تحلیل دیده
    می‌شوند — و کاربر دو روایت متفاوت از یک داده می‌بیند.
    """
    blocks: list[Block] = []
    for series in analysis.series:
        svg = charts.get(series.key)
        if series.points and svg:
            caption = f"{series.title}"
            if series.unit:
                caption += f" — واحد: {series.unit}"
            if series.note:
                #: توضیح ساخت سری باید در گزارش هم بیاید، وگرنه خوانندهٔ PDF
                #: نمی‌داند چرا جمع نمودار با جدول یکی نیست.
                caption += f" — {series.note}"
            blocks.append(Block("chart", {"svg": svg, "caption": caption,
                                          "key": series.key}))
        elif series.empty_reason:
            blocks.append(Block("callout", {
                "severity": "info", "title": series.title,
                "body": series.empty_reason}))

    for key, caption in (("donut", "سهم گروه‌ها از کل"),
                         ("scatter", "همبستگی دو ستون عددی")):
        svg = charts.get(key)
        if svg:
            blocks.append(Block("chart", {"svg": svg, "caption": caption,
                                          "key": key}))
    if not blocks:
        blocks.append(Block("callout", {
            "severity": "info", "title": "نموداری ساخته نشد",
            "body": "برای ساخت نمودار، جدول باید ستون عددی و ستون دسته‌بندی یا "
                    "تاریخ داشته باشد. در این فایل چنین ترکیبی پیدا نشد."}))
    return Section(SECTION_CHARTS, "نمودارها", blocks)


def _insight_section(analysis: Analysis) -> Section:
    """بخش بینش‌های کلیدی."""
    blocks: list[Block] = []
    if analysis.insights:
        blocks.append(Block("callouts", {"entries": [
            {"title": insight.title, "body": insight.body,
             "severity": insight.severity}
            for insight in analysis.insights
        ]}))
    else:
        blocks.append(Block("callout", {
            "severity": "info", "title": "بینشی تولید نشد",
            "body": "هیچ الگوی قابل‌اتکایی در داده پیدا نشد. بینش فقط وقتی "
                    "ساخته می‌شود که شاهد عددی داشته باشد؛ در غیر این صورت "
                    "جملهٔ تزئینی تولید نمی‌شود."}))
    blocks.append(Block("paragraph", {"text":
        "هر بینش بالا با یک شاهد عددی ساخته شده است و اعداد آن از همان جدول "
        "می‌آید. هیچ بینشی بر پایهٔ فرض یا دانش بیرونی ساخته نشده."}))
    return Section(SECTION_INSIGHTS, "بینش‌های کلیدی", blocks)


def _detail_section(profile: Profile, analysis: Analysis,
                    clean: CleanResult | None) -> Section:
    """بخش تحلیل تفصیلی — تفکیک گروه‌ها، ناهنجاری‌ها و نوسان‌ها."""
    blocks: list[Block] = []

    for breakdown in analysis.breakdowns:
        if not breakdown.rows:
            continue
        blocks.append(Block("table", {
            "columns": [breakdown.dimension, breakdown.metric, "سهم"],
            "rows": [[row["label"], row["value_text"], row["share_text"]]
                     for row in breakdown.rows],
            "caption": f"تفکیک {breakdown.metric} بر حسب {breakdown.dimension}"
                       f" — جمع کل گروه‌ها: {fa_number(breakdown.total)}",
        }))
        if breakdown.dropped:
            blocks.append(Block("callout", {
                "severity": "warning", "title": "سطرهای بدون گروه",
                "body": (f"{fa_number(breakdown.dropped)} سطر در ستون "
                         f"«{breakdown.dimension}» گروه نداشتند و در این تفکیک "
                         "شمرده نشده‌اند؛ پس جمع گروه‌ها از جمع کل جدول کمتر "
                         "است. اگر این سطرها مهم‌اند، مقدار ستون را پر کنید."),
            }))

    if profile.suspicious_total:
        rows = []
        for column in profile.columns_profile:
            for item in column.suspicious:
                rows.append([column.name, item["reason"],
                             fa_number(item["count"]),
                             fa_percent(item["ratio"])])
        if rows:
            blocks.append(Block("table", {
                "columns": ["ستون", "دلیل", "تعداد", "نسبت"],
                "rows": rows[:24],
                "caption": "مقادیر مشکوک — این‌ها فقط علامت‌گذاری شده‌اند و "
                           "حذف نشده‌اند",
            }))

    if analysis.anomalies:
        blocks.append(Block("table", {
            "columns": ["ستون", "سطر", "مقدار", "روش"],
            "rows": [[item.column, fa_number(item.row + 1), fa_compact(item.value),
                      item.method] for item in analysis.anomalies[:20]],
            "caption": "ناهنجاری‌ها — با دو روش IQR و Z-score سنجیده شده‌اند",
        }))

    correlation = analysis.correlation
    if correlation.get("columns"):
        names = correlation["columns"]
        rows = []
        for index, row in enumerate(correlation["matrix"]):
            rows.append([names[index]] + [
                "—" if value is None else fa_number(value, decimals=2)
                for value in row])
        blocks.append(Block("table", {
            "columns": [""] + names, "rows": rows,
            "caption": "همبستگی پیرسون: " + correlation.get("note", ""),
        }))
    elif correlation.get("note"):
        blocks.append(Block("callout", {"severity": "info",
                                        "title": "همبستگی محاسبه نشد",
                                        "body": correlation["note"]}))

    if clean and clean.fixes:
        blocks.append(Block("table", {
            "columns": ["اصلاح", "شرح", "تعداد"],
            "rows": [[fix.title, fix.detail, fa_number(fix.affected)]
                     for fix in clean.fixes],
            "caption": "اصلاحات اعمال‌شده در مرحلهٔ پاک‌سازی",
        }))
    if clean and clean.findings:
        blocks.append(Block("list", {
            "title": "مسائل پیداشده پیش از پاک‌سازی",
            "entries": [f"{finding.title} — {fa_number(finding.affected)} مورد"
                      for finding in clean.findings],
        }))

    if not blocks:
        blocks.append(Block("callout", {
            "severity": "info", "title": "تحلیل تفصیلی موجود نیست",
            "body": "برای تحلیل تفصیلی، جدول باید ستون گروه‌بندی یا ستون عددی "
                    "داشته باشد."}))
    return Section(SECTION_DETAIL, "تحلیل تفصیلی", blocks)


def _appendix_section(profile: Profile) -> Section:
    """پیوست — پروفایل کامل ستون‌ها."""
    rows = []
    for column in profile.columns_profile:
        rows.append([
            column.name,
            column.type_label,
            column.role_label,
            fa_number(column.filled),
            fa_number(column.missing),
            fa_number(column.unique),
            fa_percent(column.validity),
        ])
    blocks = [Block("table", {
        "columns": ["ستون", "نوع", "نقش", "پرشده", "خالی", "یکتا", "اعتبار"],
        "rows": rows,
        "caption": f"پروفایل {fa_number(profile.columns)} ستون",
    })]
    return Section(SECTION_APPENDIX, "پیوست: پروفایل ستون‌ها", blocks,
                   new_page=True)


def theme_choices() -> list[dict]:
    """فهرست تم‌ها برای انتخاب در فرم."""
    return [{"key": key, "label": value["label"],
             "description": value["description"]}
            for key, value in THEMES.items()]


def meta_payload(*, display_name: str, size_bytes: int, extension: str,
                 processed_at: str, theme_name: str, sheet: str = "",
                 encoding: str = "", separator: str = "",
                 skipped_rows: int = 0, truncated: bool = False) -> dict:
    """فرادادهٔ گزارش — همان چیزی که در سرصفحه و ذخیره‌سازی می‌نشیند."""
    return {
        "display_name": display_name,
        "size_bytes": size_bytes,
        "extension": extension,
        "processed_at": processed_at,
        "theme": theme_name,
        "theme_label": theme_of(theme_name).get("label", ""),
        "sheet": sheet,
        "encoding": encoding,
        "separator": separator,
        "skipped_rows": skipped_rows,
        "truncated": truncated,
    }


def report_styles(report: Report) -> dict:
    """متغیرهای CSS تم — رابط و PDF از یک پالت تغذیه می‌شوند."""
    theme = report.theme
    return {
        "--primary": theme["primary"],
        "--primary-dark": theme["primary_dark"],
        "--accent": theme["accent"],
        "--ink": theme["ink"],
        "--muted": theme["muted"],
        "--line": theme["line"],
        "--soft": theme["soft"],
    }


def summary_rows(report: Report) -> list[dict]:
    """خلاصهٔ بخش‌ها برای فهرست کنار صفحهٔ گزارش."""
    return [{"key": section.key, "title": section.title,
             "has_charts": any(block.kind == "chart" for block in section.blocks),
             "has_tables": any(block.kind == "table" for block in section.blocks),
             "blocks": len(section.blocks)}
            for section in report.sections]


def section_as_dict(section: Section) -> dict:
    return section.as_dict()


def block_as_dict(block: Block) -> dict:
    return asdict(block)
