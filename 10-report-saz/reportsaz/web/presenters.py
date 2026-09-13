# -*- coding: utf-8 -*-
"""مبدل‌های نمایش — از دادهٔ خام تا چیزی که قالب می‌تواند بکشد.

دو کار اینجا انجام می‌شود:

۱) **ساخت مدل نمایش.** قالب‌ها منطق ندارند: هیچ‌جا در HTML شرط «اگر متریک
   بود» نوشته نمی‌شود. هر چیزی که قالب لازم دارد — از کلاس رنگ تا متن خالی —
   اینجا آماده می‌شود.

۲) **رندر نمودار SVG.** نمودارها سمت سرور ساخته می‌شوند؛ مرورگر فقط HTML و
   CSS می‌گیرد. برای هر نمودار یک «جدول جانشین» هم ساخته می‌شود تا داده‌ای که
   در تصویر است، برای جست‌وجو، کپی و صفحه‌خوان هم در دسترس باشد.
"""
from __future__ import annotations

import re

from ..analytics import Analysis
from ..charts import (SVG_WIDTH, build_bar_geometry, build_geometry,
                      build_line_geometry, empty_chart, svg_bar, svg_donut,
                      svg_histogram, svg_line, svg_scatter)
from ..cleaning import CleanOptions, CleanResult, options_meta
from ..config import MAX_UPLOAD_MB, QUALITY_METHOD, QUALITY_WEIGHTS, QUALITY_BANDS
from ..labels import (fa_bytes, fa_compact, fa_number, fa_percent,
                      to_persian_digits)
from ..profile import Profile
from ..report import Report, summary_rows, theme_choices
from .context import STAGES, Bundle


# ------------------------------------------------------------------ نوار گام‌ها
def stage_rail(bundle: Bundle | None, active: str) -> list[dict]:
    """وضعیت گام‌های پردازش برای نمایش در بالای صفحه."""
    order = [item["key"] for item in STAGES]
    reached = bundle.stage() if bundle is not None else ""
    try:
        reached_index = order.index("reached") if reached == "reached" else \
            order.index(reached) if reached in order else -1
    except ValueError:
        reached_index = -1
    try:
        active_index = order.index(active)
    except ValueError:
        active_index = -1

    rail: list[dict] = []
    for index, item in enumerate(STAGES):
        state = "todo"
        if index < active_index:
            state = "done"
        elif index == active_index:
            state = "current"
        elif index <= reached_index:
            state = "done"
        rail.append({
            "key": item["key"], "label": item["label"], "icon": item["icon"],
            "state": state,
            "url": _stage_url(bundle.dataset_id if bundle else None,
                              item["key"]),
        })
    return rail


def _stage_url(dataset_id: str | None, key: str) -> str:
    if not dataset_id:
        return ""
    mapping = {
        "uploaded": f"/dataset/{dataset_id}/inspect",
        "inspected": f"/dataset/{dataset_id}/inspect",
        "cleaned": f"/dataset/{dataset_id}/clean",
        "analysed": f"/dataset/{dataset_id}/dashboard",
        "reported": f"/dataset/{dataset_id}/report",
    }
    return mapping.get(key, "")


# ------------------------------------------------------------------ صفحه‌ها
def landing_view(demo_meta: dict) -> dict:
    """مدل صفحهٔ خانه — محصول، گردش کار و قابلیت‌ها."""
    workflow = [
        {"title": "بارگذاری", "body":
         f"فایل XLSX یا CSV تا {fa_number(MAX_UPLOAD_MB)} مگابایت. بررسی "
         "پسوند، محتوا و حجم پیش از هر پردازشی."},
        {"title": "بازرسی", "body":
         "پروفایل کامل: نوع و نقش هر ستون، سلول‌های خالی، ردیف‌های تکراری و "
         "مقدارهای مشکوک — پیش از هر تغییری در داده."},
        {"title": "پاک‌سازی شفاف", "body":
         "هر مسئله با شمار دقیقش نشان داده می‌شود و هر اصلاح با اجازهٔ شما "
         "اعمال می‌شود. حذف بی‌اعلام وجود ندارد."},
        {"title": "تحلیل", "body":
         "شاخص‌های کلیدی، تفکیک گروه‌ها، روند، توزیع، ناهنجاری و همبستگی — "
         "همه از همان جدول."},
        {"title": "گزارش", "body":
         "پیش‌نمایش گزارش و خروجی PDF و اکسل قالب‌بندی‌شده، در سه تم."},
    ]
    capabilities = [
        {"title": "شناسایی خودکار نوع ستون",
         "body": "عدد، متن، تاریخ و شناسه — با نسبت اعتبار هر ستون."},
        {"title": "تاریخ شمسی و میلادی",
         "body": "تاریخ‌های شمسی، قالب «۵ مهر ۱۴۰۳» و ارقام فارسی همه تجزیه "
                 "می‌شوند."},
        {"title": "عدد در متن",
         "body": "«۱٬۲۰۰٬۰۰۰ ریال»، «۲۵۰ هزار» و «(۳٬۲۰۰)» به منفی — همه به "
                 "عدد واقعی تبدیل می‌شوند."},
        {"title": "امتیاز کیفیت داده",
         "body": "چهار زیرامتیاز وزن‌دار با روش اعلام‌شده."},
        {"title": "تشخیص ناهنجاری",
         "body": "دو روش IQR و Z-score با هم، هر کدام با دلیلش."},
        {"title": "گزارش PDF و اکسل",
         "body": "PDF چندصفحه‌ای با متن فارسی صحیح و کارپوشهٔ اکسل "
                 "قالب‌بندی‌شده."},
    ]
    guarantees = [
        "هیچ عددی ساخته نمی‌شود: اگر ستون مناسبی نباشد، آن بخش خالی می‌ماند و "
        "دلیلش گفته می‌شود.",
        "فایل بارگذاری‌شده هرگز اجرا نمی‌شود؛ فقط با کتابخانه‌های خواندن داده "
        "باز می‌شود.",
        "بسته‌های پردازش خودکار پاک می‌شوند؛ حافظهٔ سرور برای فایل شما "
        "نگه‌داشته نمی‌ماند.",
        "فایل روی دیسک سرور می‌ماند تا خروجی PDF و اکسل ساخته شود، و پس از "
        "پایان عمر بسته حذف می‌شود.",
    ]
    return {
        "workflow": workflow, "capabilities": capabilities,
        "guarantees": guarantees,
        "formats": [{"name": "XLSX", "note": "اکسل ۲۰۰۷ و بعد"},
                    {"name": "CSV", "note": "UTF-8، UTF-8 با BOM و CP1256"}],
        "limits": {
            "size": f"{fa_number(MAX_UPLOAD_MB)} مگابایت",
            "quality_method": QUALITY_METHOD,
            "themes": theme_choices(),
        },
        "demo": demo_meta,
    }


def inspect_view(bundle: Bundle, profile: Profile, read: dict,
                 findings: list) -> dict:
    """مدل صفحهٔ بازرسی — پروفایل، پیش‌نمایش و مسائل."""
    frame = bundle.raw_frame()
    preview = _preview(frame)
    columns = [_column_card(column) for column in profile.columns_profile]
    return {
        "profile": profile,
        "columns": columns,
        "quality": _quality_view(profile),
        "read": read,
        "findings": [item.as_dict() if hasattr(item, "as_dict") else item
                     for item in findings],
        "preview": preview,
        "roles": _role_summary(profile),
        "meta": meta_view(bundle),
    }


def clean_view(bundle: Bundle, profile: Profile, options: CleanOptions,
               clean_result: CleanResult | None) -> dict:
    """مدل صفحهٔ پاک‌سازی — مسائل، گزینه‌ها و اصلاحات اعمال‌شده."""
    frame = bundle.raw_frame()
    detection = bundle.meta.get("findings", [])
    applied = clean_result.as_dict() if clean_result else \
        (bundle.meta.get("cleaning") or {})
    return {
        "options": options_meta(),
        "selected": options.as_dict(),
        "findings": detection,
        "applied": applied if bundle.reached("cleaned") else None,
        "profile_before": profile,
        "quality_after": _quality_view(profile) if bundle.reached("cleaned") else None,
        "preview_before": _preview(frame),
        "preview_after": _preview(bundle.working_frame())
        if bundle.reached("cleaned") else None,
        "meta": meta_view(bundle),
    }


def dashboard_view(bundle: Bundle, profile: Profile, analysis: Analysis) -> dict:
    """مدل صفحهٔ تحلیل — شاخص‌ها، بینش‌ها و نمودارها."""
    charts = render_charts(analysis, bundle)
    frame = bundle.working_frame()
    return {
        "profile": profile,
        "analysis": analysis,
        "charts": charts,
        "kpis": [kpi.as_dict() for kpi in analysis.kpis],
        "insights": [_insight_view(item) for item in analysis.insights],
        "anomalies": [item.as_dict() for item in analysis.anomalies],
        "breakdowns": [item.as_dict() for item in analysis.breakdowns],
        "correlation": correlation_rows(analysis.correlation),
        "notes": analysis.notes,
        "movers": _movers_view(frame, analysis),
        "meta": meta_view(bundle),
        "themes": theme_choices(),
        "theme": bundle.meta.get("theme", "corporate"),
        "selection": {
            "metric": analysis.primary_metric,
            "dimension": analysis.primary_dimension,
            "date": analysis.date_column,
        },
        "metrics": [column.name for column in profile.metrics()],
        "dimensions": [column.name for column in profile.dimensions()],
        "dates": [column.name for column in profile.dates()],
    }


def report_view(bundle: Bundle, report: Report, analysis: Analysis) -> dict:
    """مدل صفحهٔ گزارش — بخش‌ها، فهرست و تم."""
    return {
        "report": report,
        "analysis": analysis,
        "sections": summary_rows(report),
        "meta": meta_view(bundle),
        "themes": theme_choices(),
        "theme": bundle.meta.get("theme", "corporate"),
        "exports": {
            "pdf": f"/dataset/{bundle.dataset_id}/export/pdf",
            "excel": f"/dataset/{bundle.dataset_id}/export/excel",
        },
    }


# ------------------------------------------------------------------ نمودارها
def render_charts(analysis: Analysis, bundle: Bundle) -> dict:
    """ساخت SVG نمودارها از سری‌های تحلیل.

    هر نمودار کلید خودش را دارد و اگر داده نداشته باشد، *جایگزین با دلیل*
    برمی‌گرداند — نمودار ساختگی هرگز ساخته نمی‌شود.
    """
    theme = _palette(bundle)
    charts: dict[str, dict] = {}

    for series in analysis.series:
        labels = [point.label for point in series.points]
        values = [point.value for point in series.points]
        if not series.points:
            charts[series.key] = {
                "svg": empty_chart(series.empty_reason or "داده‌ای برای این نمودار نیست.",
                                   theme),
                "title": series.title, "empty": True,
                "reason": series.empty_reason, "table": None,
                "key": series.key, "note": "",
            }
            continue

        if series.key == "trend":
            geometry = build_line_geometry(labels, values)
            svg = svg_line(labels, values, geometry, theme, title=series.title,
                           unit=series.unit)
            table = {"columns": [series.unit or "برچسب", series.title],
                     "rows": [[label, fa_compact(value)]
                              for label, value in zip(labels, values)]}
        elif series.key == "breakdown":
            points = [(point.label, point.value, fa_compact(point.value))
                      for point in series.points]
            geometry, centers = build_bar_geometry([item[0] for item in points],
                                                   [item[1] for item in points])
            svg = svg_bar(points, geometry, centers, theme, title=series.title)
            total = series.total or 1
            table = {"columns": [analysis.primary_dimension, series.title, "سهم"],
                     "rows": [[point.label, fa_compact(point.value),
                               fa_percent(point.value / total)]
                              for point in series.points]}
        else:
            points = [(point.label, point.value, fa_compact(point.value))
                      for point in series.points]
            geometry = build_geometry([item[0] for item in points],
                                      [item[1] for item in points])
            svg = svg_histogram(points, geometry, theme, title=series.title)
            table = {"columns": ["بازه", series.title],
                     "rows": [[point.label, fa_number(point.value)]
                              for point in series.points]}

        charts[series.key] = {"svg": svg, "title": series.title, "empty": False,
                              "reason": "", "table": table,
                              "key": series.key, "note": series.note}

    #: حلقه‌ای: فقط وقتی سهم گروه‌ها معنا دارد (حداقل دو گروه، نه بیشتر از شش).
    if analysis.breakdowns and analysis.breakdowns[0].rows:
        rows = analysis.breakdowns[0].rows
        if 2 <= len(rows) <= 6:
            points = [(row["label"], row["value"], row["value_text"],
                       row["share_text"]) for row in rows]
            charts["donut"] = {
                "svg": svg_donut(points, theme, title="سهم گروه‌ها",
                                 center_label=fa_compact(
                                     analysis.breakdowns[0].total)),
                "title": "سهم گروه‌ها", "empty": False, "reason": "",
                "key": "donut", "note": "",
                "table": {"columns": [analysis.breakdowns[0].dimension,
                                      analysis.breakdowns[0].metric, "سهم"],
                          "rows": [[row["label"], row["value_text"],
                                    row["share_text"]] for row in rows]},
            }

    #: پراکندگی همبستگی — دو متریک اول.
    correlation = analysis.correlation
    if correlation.get("columns") and len(correlation["columns"]) >= 2:
        from ..analytics import _numeric

        frame = bundle.working_frame()
        if frame is not None:
            names = correlation["columns"][:2]
            x_values = _numeric(frame, names[0]).tolist()
            y_values = _numeric(frame, names[1]).tolist()
            geometry = build_geometry([], y_values or [0.0])
            charts["scatter"] = {
                "svg": svg_scatter(x_values, y_values, geometry, theme,
                                   title=f"{names[1]} در برابر {names[0]}",
                                   x_label=names[0], y_label=names[1]),
                "title": f"{names[1]} در برابر {names[0]}", "empty": False,
                "reason": "", "table": None, "key": "scatter", "note": "",
            }
    return charts


def _palette(bundle: Bundle) -> dict:
    from ..config import theme as theme_of

    return theme_of(bundle.meta.get("theme"))


# ------------------------------------------------------------------ کمکی‌ها
def _preview(frame, limit: int = 12) -> dict | None:
    """پیش‌نمایش جدول — سقف ستون و سطر تا صفحه سنگین نشود."""
    if frame is None or frame.empty:
        return None
    columns = [str(name) for name in list(frame.columns)[:14]]
    rows = []
    for _, record in frame.head(limit).iterrows():
        rows.append([_cell(record[name]) for name in columns])
    return {"columns": columns, "rows": rows,
            "hidden_columns": max(0, frame.shape[1] - len(columns)),
            "total_rows": int(len(frame))}


#: متنی که *خودش* یک عدد است — با جداکنندهٔ لاتین یا فارسی.
_NUMERIC_TEXT = re.compile(r"^\s*[+-]?[0-9][0-9,٬\u00a0]*(?:\.[0-9]+)?\s*$")


def _cell(value) -> str:
    """یک سلول برای نمایش — مقدار خالی با نشانهٔ خوانا.

    رقم لاتین در متن فارسی خواندن را بد می‌کند و در کل محصول جایی ندارد، پس
    همان تبدیل لبهٔ نمایش روی سلول‌های پیش‌نمایش هم اعمال می‌شود. عددهای واقعی
    با جداکننده و ممیز فارسی می‌آیند؛ متن‌هایی که فقط رقم دارند (شناسه، تاریخ)
    تنها رقم‌شان فارسی می‌شود تا ساختارشان دست‌نخورده بماند.
    """
    if value is None:
        return ""
    text = str(value)
    if text in ("nan", "NaT", "<NA>"):
        return ""
    return _display_value(text)[:48]


def _display_value(text: str) -> str:
    """نمایش یک مقدار خام با رقم فارسی، و عدد اگر عدد بود."""
    stripped = text.strip()
    if not stripped:
        return ""
    if not _NUMERIC_TEXT.match(stripped):
        return to_persian_digits(text)
    plain = stripped.replace(",", "").replace("٬", "").replace("\u00a0", "")
    try:
        number = float(plain)
    except ValueError:
        return to_persian_digits(text)
    decimals = len(plain.split(".", 1)[1]) if "." in plain else 0
    return fa_number(number, decimals=decimals)


def _role_summary(profile: Profile) -> dict:
    counts: dict[str, int] = {}
    for column in profile.columns_profile:
        counts[column.role_label] = counts.get(column.role_label, 0) + 1
    return {"counts": [{"label": label, "count": fa_number(count)}
                       for label, count in counts.items()],
            "metrics": [column.name for column in profile.metrics()],
            "dimensions": [column.name for column in profile.dimensions()],
            "dates": [column.name for column in profile.dates()]}


def _column_card(column) -> dict:
    """کارت یک ستون در صفحهٔ بازرسی."""
    payload = column.as_dict()
    payload["fill_text"] = fa_percent(column.fill_ratio)
    payload["validity_text"] = fa_percent(column.validity)
    payload["missing_text"] = fa_number(column.missing)
    payload["unique_text"] = fa_number(column.unique)
    payload["bar_width"] = round(max(1.0, column.fill_ratio * 100), 1)

    if column.type == "number" and column.total is not None:
        payload["summary"] = f"جمع: {fa_compact(column.total)}"
    elif column.date_min and column.date_max:
        #: تاریخ به شکل ISO ذخیره شده و تاریخ *نمایش* با رقم فارسی نوشته
        #: می‌شود؛ وگرنه عدد لاتین در متن فارسی می‌ماند.
        payload["summary"] = (f"از {to_persian_digits(column.date_min)} "
                             f"تا {to_persian_digits(column.date_max)}")
    elif column.top_value:
        payload["summary"] = f"رایج‌ترین: {to_persian_digits(column.top_value)}"
    else:
        payload["summary"] = ""
    return payload


def _quality_view(profile: Profile) -> dict:
    """نمای امتیاز کیفیت — با وزن‌ها و روش کار."""
    quality = profile.quality
    parts = quality.get("parts", {})
    labels = {"completeness": "کامل‌بودن", "validity": "اعتبار",
              "uniqueness": "یکتایی", "consistency": "یکدستی"}
    details = {"completeness": "نسبت سلول‌های پرشده به کل سلول‌ها",
               "validity": "نسبت سلول‌هایی که با نوع ستون می‌خوانند",
               "uniqueness": "نسبت ردیف‌های غیرتکراری",
               "consistency": "یکسان بودن قالب نمایش در هر ستون"}
    items = []
    for key, weight in QUALITY_WEIGHTS.items():
        value = float(parts.get(key, 0))
        items.append({
            "key": key, "label": labels.get(key, key),
            "value": value, "value_text": fa_number(value, decimals=1),
            "weight_text": fa_percent(weight),
            "detail": details.get(key, ""),
            "band": _band(value),
        })
    score = float(quality.get("score", 0))
    return {
        "score": score, "score_text": fa_number(score, decimals=1),
        "label": quality.get("label", ""),
        "band": _band(score),
        #: کلید عمداً ``parts`` است و نه ``items``: در ژنجا دسترسی ``obj.items``
        #: اول متد دیکشنری را پیدا می‌کند و فهرست هرگز دیده نمی‌شود.
        "parts": items,
        "method": QUALITY_METHOD,
        "bands": [{"label": label, "threshold": fa_number(threshold)}
                  for threshold, label in QUALITY_BANDS],
    }


def _band(value: float) -> str:
    """برچسب رنگ بر اساس آستانه‌های اعلام‌شده."""
    for threshold, label in QUALITY_BANDS:
        if value >= threshold:
            return {"عالی": "great", "خوب": "good", "قابل قبول": "fair",
                    "ضعیف": "weak"}.get(label, "fair")
    return "weak"


def _movers_view(frame, analysis: Analysis) -> dict:
    """بیشترین رشد و کاهش گروه‌ها بین دو نیمهٔ بازه."""
    from ..analytics import movers

    if frame is None or not (analysis.primary_metric and analysis.date_column
                             and analysis.primary_dimension):
        return {"gainers": [], "losers": [], "reason":
                "برای مقایسهٔ دوره‌ها به ستون تاریخ، متریک و بعد نیاز است."}
    return movers(frame, analysis.primary_metric, analysis.date_column,
                  analysis.primary_dimension)


#: نام فارسی کلیدهای شاهد عددی — کلیدهای انگلیسی نباید در رابط فارسی دیده
#: شوند، همان‌قدر که عدد لاتین نباید دیده شود.
EVIDENCE_LABELS = {
    "dimension": "بعد", "metric": "متریک", "label": "گروه",
    "share": "سهم", "value": "مقدار", "total": "جمع کل",
    "recent": "نیمهٔ دوم", "previous": "نیمهٔ اول", "ratio": "نسبت تغییر",
    "date_column": "ستون تاریخ", "column": "ستون", "missing": "تعداد خالی",
    "duplicates": "تعداد تکراری", "row": "سطر", "score": "امتیاز انحراف",
    "method": "روش", "groups": "تعداد گروه", "small": "گروه کم‌سهم",
}
#: کلیدهایی که مقدارشان نسبت است و باید درصد نمایش داده شوند.
PERCENT_KEYS = {"share", "ratio"}


def evidence_items(evidence: dict) -> list[dict]:
    """شاهد عددی یک بینش — برچسب فارسی و مقدار قالب‌بندی‌شده.

    بدون این تبدیل، مقادیری مثل ``0.3390927779309053`` خام روی صفحه می‌آمد.
    """
    items: list[dict] = []
    for key, value in (evidence or {}).items():
        if value is None:
            continue
        label = EVIDENCE_LABELS.get(key, key)
        if key in PERCENT_KEYS and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            text = fa_percent(value, signed=(key == "ratio"))
        elif isinstance(value, bool):
            text = "بله" if value else "خیر"
        elif isinstance(value, float):
            text = fa_number(value, decimals=2)
        elif isinstance(value, int):
            text = fa_number(value)
        else:
            text = str(value)
        items.append({"label": label, "value": text})
    return items


def _insight_view(insight) -> dict:
    """یک بینش برای نمایش — با شاهد عددی قالب‌بندی‌شده."""
    payload = insight.as_dict()
    payload["evidence_items"] = evidence_items(payload.get("evidence") or {})
    return payload


def correlation_rows(correlation: dict) -> dict:
    """جدول آمادهٔ همبستگی — با اعداد فارسی و رمزگذاری رنگ.

    قالب نباید فیلتر روی فیلتر بگذارد؛ تبدیل اینجا انجام می‌شود.
    """
    names = correlation.get("columns") or []
    matrix = correlation.get("matrix") or []
    rows = []
    for index, row in enumerate(matrix):
        cells = []
        for value in row:
            if value is None:
                cells.append({"text": "—", "tone": "none"})
                continue
            tone = "none"
            if abs(value) >= 0.7:
                tone = "strong-pos" if value > 0 else "strong-neg"
            elif abs(value) >= 0.4:
                tone = "mild-pos" if value > 0 else "mild-neg"
            cells.append({"text": fa_number(value, decimals=2), "tone": tone})
        rows.append({"label": names[index] if index < len(names) else "—",
                     "cells": cells})
    return {"columns": names, "rows": rows, "note": correlation.get("note", "")}


def meta_view(bundle: Bundle) -> dict:
    """فرادادهٔ کوتاه بسته برای نمایش در سرصفحهٔ صفحه‌ها."""
    meta = bundle.meta
    read = meta.get("read") or {}
    return {
        "id": bundle.dataset_id,
        "display_name": meta.get("display_name", "—"),
        "size_text": fa_bytes(meta.get("size_bytes", 0)),
        "extension": (meta.get("extension") or "").upper(),
        "created_at": meta.get("created_at", ""),
        "stage": meta.get("stage", ""),
        "warnings": list(meta.get("warnings", [])),
        "sheet": read.get("sheet", ""),
        "encoding": read.get("encoding", ""),
        "separator": read.get("separator", ""),
        "truncated": bool(read.get("truncated")),
    }
