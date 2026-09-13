# -*- coding: utf-8 -*-
"""آماده‌سازی داده برای نمایش — تنها جایی که از عدد خام، نمودار و جدول می‌سازد.

قالب‌ها هیچ محاسبه‌ای نمی‌کنند و ماژول‌های تحلیل هم چیزی دربارهٔ HTML نمی‌دانند.
اینجا مرز است: هر چیزی که صفحه لازم دارد، آماده و قالب‌بندی‌شده از این توابع
بیرون می‌آید.
"""
from __future__ import annotations

from .. import services
from ..charts import Bar, columns, grouped_bars, histogram, horizontal_bars, legend, stacked_share
from ..config import LABELS
from ..labels import fa_datetime, fa_number, fa_percent, sentiment_label

#: رنگ هر کلاس — یک منبع حقیقت تا رنگ در همهٔ نمودارها و نشانه‌ها یکی باشد.
CLASS_COLOR = {
    "pos": "var(--label-pos)",
    "neu": "var(--label-neu)",
    "neg": "var(--label-neg)",
}


def class_legend() -> str:
    return legend([(sentiment_label(code), CLASS_COLOR[code]) for code in LABELS])


# ------------------------------------------------------------------ کارت‌ها
def summary_cards() -> list[dict]:
    """کارت‌های شاخص بالای صفحهٔ «تحلیل» — از عدد خام لایهٔ تحلیل."""
    data = services.summary_cards()
    return [
        {"label": "نمونه‌های دیتاست", "value": fa_number(data["n_samples"]),
         "hint": "سینتتیک"},
        {"label": "اندازهٔ واژگان", "value": fa_number(data["vocabulary_size"]),
         "hint": "ویژگی TF-IDF"},
        {"label": "میانگین طول کامنت",
         "value": fa_number(data["mean_length"], decimals=1),
         "hint": "توکن معنادار"},
        {"label": "کلاس‌ها", "value": fa_number(data["class_count"]),
         "hint": "مثبت، خنثی، منفی"},
    ]


# ------------------------------------------------------------------ نمای کلی
def balance_chart() -> str:
    """شمار نمونهٔ هر کلاس در دیتاست نمونه."""
    from .. import analytics

    counts = analytics.actual_mix(services.dataset())["counts"]
    bars = [Bar(label=sentiment_label(code), value=float(counts[code]),
                display=fa_number(counts[code]), color=CLASS_COLOR[code],
                hint=f"{sentiment_label(code)}: {fa_number(counts[code])} نمونه")
            for code in LABELS]
    return horizontal_bars(bars, title="شمار نمونه در هر کلاس", show_values=True)


def overview_numbers() -> list[dict]:
    """کارت‌های نمای کلی — همه از معیارهای ذخیره‌شده، بدون بیدار کردن مدل."""
    data = services.metrics()
    in_domain = data["in_domain"]
    out_domain = data["out_domain"]
    return [
        {"label": "نمونه‌های دیتاست", "value": fa_number(data["n_samples"]),
         "hint": "آموزش + آزمون"},
        {"label": "F1 درون‌توزیع", "value": fa_percent(in_domain["f1_macro"]),
         "hint": "آزمون روی دادهٔ هم‌توزیع"},
        {"label": "F1 بیرون‌از‌توزیع", "value": fa_percent(out_domain["f1_macro"]),
         "hint": f"روی {fa_number(data['stress_n'])} نمونهٔ دست‌نویس"},
        {"label": "اندازهٔ واژگان", "value": fa_number(data["vocabulary_size"]),
         "hint": "ویژگی TF-IDF"},
    ]


def model_ranking() -> list[dict]:
    """مقایسهٔ سه نامزد — با هر دو عدد، چون اختلافشان خودش یافته است."""
    data = services.metrics()
    best = data["best_model"]
    rows = []
    for name, values in data["results"].items():
        rows.append({
            "name": name,
            "is_best": name == best,
            "f1": fa_percent(values["f1_macro"]),
            "accuracy": fa_percent(values["accuracy"]),
            "stress_f1": fa_percent(values["stress_f1_macro"]),
            "gap": fa_percent(values["f1_macro"] - values["stress_f1_macro"]),
            "fit_seconds": fa_number(values["fit_seconds"], decimals=2),
        })
    return rows


# ------------------------------------------------------------------ تحلیل متن
def probability_chart(result: dict) -> str:
    """احتمال هر کلاس برای یک متن — با رنگ همان کلاس."""
    proba = result.get("proba") or {}
    bars = [Bar(label=sentiment_label(code), value=float(proba.get(code, 0.0)) * 100,
                display=fa_percent(proba.get(code, 0.0), decimals=1),
                color=CLASS_COLOR[code],
                hint=f"{sentiment_label(code)}: {fa_percent(proba.get(code, 0.0), decimals=1)}")
            for code in LABELS]
    return horizontal_bars(bars, unit="٪", decimals=1, row_height=32,
                           label_width=96, title="احتمال هر کلاس")


def signal_rows(signals: list[dict]) -> list[dict]:
    """نوارهای واژه‌های مؤثر — HTML ساده، نه SVG.

    دلیلش دسترس‌پذیری است: این نوارها متن هستند و باید قابل انتخاب و خوانده‌شدن
    با صفحه‌خوان باشند؛ داخل SVG این‌ها سخت‌تر به دست می‌آید.
    """
    rows = []
    for signal in signals:
        rows.append({
            "term": signal["term"],
            "is_phrase": signal.get("is_phrase", False),
            "width": max(0.04, float(signal.get("share", 0.0))),
            "score": fa_number(signal.get("score", 0.0), decimals=2),
        })
    return rows


def analyze_view(result: dict) -> dict:
    """همهٔ چیزی که صفحهٔ تحلیل متن لازم دارد."""
    return {
        "has_input": bool(result.get("text", "").strip()),
        "state": result["state"],
        "state_note": _state_note(result),
        "label": result["label"],
        "label_fa": sentiment_label(result["label"]),
        "label_code": result["label"],
        "confidence": result["confidence"],
        "confidence_fa": fa_percent(result["confidence"]),
        "band": result["band"],
        "verdict": result["verdict"],
        "chart": probability_chart(result),
        "toward": signal_rows(result["toward"]),
        "against": signal_rows(result["against"]),
        "has_signals": result["has_signals"],
        "coverage_fa": fa_percent(result["coverage"], decimals=0),
        "coverage": result["coverage"],
        "cleaned": result["cleaned"],
        "token_count": result["token_count"],
        "known_count": result["known_count"],
        "unknown": result["unknown_tokens"][:12],
        "known": result["known_tokens"][:12],
    }


def _state_note(result: dict) -> str:
    state = result["state"]
    if state == "empty":
        return "متنی وارد نشده است."
    if state == "no_signal":
        return ("متن هیچ توکن معناداری ندارد — همهٔ واژه‌هایش ایستا یا نشانه "
                "بودند. برچسبی گزارش نمی‌شود، چون بردار ویژگی خالی است.")
    if state == "out_of_domain":
        return ("هیچ‌یک از واژه‌های این متن در واژگان مدل نیست؛ یعنی مدل روی "
                "چنین متنی هیچ چیزی یاد نگرفته. برچسب گزارش نمی‌شود.")
    if state == "thin_coverage":
        return ("کمتر از نیمی از واژه‌های متن در واژگان مدل هست. در اندازه‌گیری "
                "همین پروژه، دقت مدل در چنین متنی به‌شدت پایین می‌آید — عدد "
                "اطمینان را جدی نگیرید.")
    return ""


# ------------------------------------------------------------------ تحلیل گروهی
def batch_share_chart(summary: dict) -> str:
    parts = [(sentiment_label(code), float(summary["counts"][code]), CLASS_COLOR[code])
             for code in LABELS]
    return stacked_share(parts, title="ترکیب برچسب‌ها")


def batch_confidence_chart(summary: dict) -> str:
    """توزیع اطمینان روی فایل بارگذاری‌شده.

    از کش استفاده نمی‌کند چون ورودی هر بار فرق دارد؛ روی فایلی تا ۵۰۰۰ ردیف،
    محاسبه‌اش چند میلی‌ثانیه است.
    """
    return ""


# ------------------------------------------------------------------ تحلیل
def mix_comparison_chart() -> str:
    """واقعی در برابر پیش‌بینی‌شده — میله‌های گروهی به تفکیک کلاس."""
    data = services.mix()
    categories = [sentiment_label(code) for code in LABELS]
    actual = [data["actual"]["shares"][code] * 100 for code in LABELS]
    predicted = [data["predicted"]["shares"][code] * 100 for code in LABELS]
    return grouped_bars(
        categories,
        [("واقعی", actual, "var(--chart-2)"),
         ("پیش‌بینی‌شده", predicted, "var(--chart-1)")],
        unit="٪", decimals=0, title="ترکیب واقعی در برابر پیش‌بینی‌شده")


def monthly_chart() -> str:
    """سهم هر کلاس در هر ماه — روند خودِ دیتاست نمونه."""
    rows = services.monthly()
    if not rows:
        return ""
    categories = [row["title"] for row in rows]
    series = [
        (sentiment_label(code),
         [row["shares"][code] * 100 for row in rows],
         CLASS_COLOR[code])
        for code in LABELS
    ]
    return grouped_bars(categories, series, unit="٪", decimals=0,
                        title="سهم کلاس‌ها در هر ماه")


def confidence_chart() -> str:
    return histogram(services.confidence_distribution(), unit="٪", x_decimals=0,
                     label_every=2, color="var(--chart-1)",
                     title="توزیع اطمینان پیش‌بینی‌ها")


def length_chart() -> str:
    return histogram(services.length_distribution(), x_decimals=0, label_every=2,
                     color="var(--chart-3)",
                     title="توزیع طول کامنت‌ها (توکن معنادار)")


def terms_chart(code: str) -> str:
    """واژگان متمایزکنندهٔ یک کلاس.

    عددها عمداً نوشته نمی‌شوند: این امتیاز نسبی است، نه احتمال. نوشتنش به شکل
    درصد، کاربر را به اشتباه می‌اندازد.
    """
    terms = services.class_terms().get(code, [])
    label = sentiment_label(code)
    bars = [Bar(label=item["term"], value=float(item["score"]),
                color=CLASS_COLOR[code],
                hint=f"{item['term']} — امتیاز نسبی {fa_number(item['score'], decimals=2)}")
            for item in terms]
    # عنوان شامل نام کلاس است؛ دو نمودار این بخش کنار هم می‌آیند و اگر نامشان
    # یکی باشد، صفحه‌خوان نمی‌تواند تشخیص دهد کدام مال کدام کلاس است.
    return horizontal_bars(bars, row_height=30, label_width=170,
                           title=f"واژگان متمایزکنندهٔ کلاس {label}",
                           show_values=False)


def coverage_chart() -> str:
    """دقت مدل به تفکیک پوشش واژگان — روی مجموعهٔ دست‌نویس."""
    buckets = [bucket for bucket in services.coverage_buckets() if bucket["n"]]
    if not buckets:
        return ""
    bars = [Bar(label=f"{bucket['title']} ({fa_number(bucket['n'])} نمونه)",
                value=float(bucket["accuracy"] or 0.0) * 100,
                display=fa_percent(bucket["accuracy"] or 0.0, decimals=0))
            for bucket in buckets]
    return horizontal_bars(bars, unit="٪", decimals=0, row_height=36,
                           label_width=210, title="دقت بر پایهٔ پوشش واژگان")


def coverage_rows() -> list[dict]:
    rows = []
    for bucket in services.coverage_buckets():
        rows.append({
            "title": bucket["title"],
            "n": fa_number(bucket["n"]),
            "accuracy": ("—" if bucket["accuracy"] is None
                         else fa_percent(bucket["accuracy"], decimals=0)),
        })
    return rows


def mix_table() -> list[dict]:
    """جدول ترکیب واقعی/پیش‌بینی‌شده با شمار و سهم."""
    data = services.mix()
    rows = []
    for code in LABELS:
        rows.append({
            "label": sentiment_label(code),
            "code": code,
            "actual_count": fa_number(data["actual"]["counts"][code]),
            "actual_share": fa_percent(data["actual"]["shares"][code]),
            "predicted_count": fa_number(data["predicted"]["counts"][code]),
            "predicted_share": fa_percent(data["predicted"]["shares"][code]),
        })
    return rows


def misclassification_rows() -> list[dict]:
    rows = []
    for item in services.misclassifications():
        rows.append({
            "text": item["text"],
            "expected": item["expected"],
            "expected_code": item["expected_code"],
            "predicted": item["predicted"],
            "predicted_code": item["predicted_code"],
            "confidence": fa_percent(item["confidence"], decimals=0),
            "unknown_ratio": fa_percent(item["unknown_ratio"], decimals=0),
        })
    return rows


def hard_case_rows() -> list[dict]:
    rows = []
    for item in services.hard_cases():
        rows.append({
            "text": item["text"],
            "label_fa": sentiment_label(item["label"]),
            "label_code": item["label"],
            "confidence": fa_percent(item["confidence"], decimals=0),
            "band": item["band"],
            "verdict": item["verdict"],
            "state": item["state"],
        })
    return rows


def metric_highlights() -> list[dict]:
    data = services.metrics()
    interval = data.get("out_domain", {})
    cv = data.get("cv", {})
    return [
        {"label": "مدل انتخاب‌شده", "value": data["best_model"]},
        {"label": "F1 بیرون‌از‌توزیع", "value": fa_percent(interval.get("f1_macro", 0))},
        {"label": "اعتبارسنجی متقابل", "value": fa_percent(cv.get("f1_macro_mean", 0))},
        {"label": "انحراف معیار CV", "value": fa_number(cv.get("f1_macro_std", 0), decimals=3)},
        {"label": "آموزش در", "value": fa_number(data["results"][data["best_model"]]["fit_seconds"], decimals=2) + " ثانیه"},
        #: مهر زمانی روی دیسک لاتین است؛ آنچه کاربر می‌خواند باید فارسی باشد.
        {"label": "زمان آموزش", "value": fa_datetime(data["trained_at"])},
    ]


def class_report_rows() -> list[dict]:
    rows = []
    for code in LABELS:
        in_domain = services.metrics()["in_domain"]["per_class"][code]
        rows.append({
            "label": sentiment_label(code),
            "code": code,
            "precision": fa_percent(in_domain["precision"]),
            "recall": fa_percent(in_domain["recall"]),
            "f1": fa_percent(in_domain["f1"]),
        })
    return rows


def unknown_rows() -> list[dict]:
    return [{"term": item["term"], "count": fa_number(item["count"]),
             "share": fa_percent(item["share"])}
            for item in services.unknown_terms()]


def columns_chart() -> str:
    """شمار نمونه در هر کلاس — نسخهٔ ستونی برای صفحهٔ متدولوژی."""
    from .. import analytics

    counts = analytics.actual_mix(services.dataset())["counts"]
    bars = [Bar(label=sentiment_label(code), value=float(counts[code]),
                display="", color=CLASS_COLOR[code]) for code in LABELS]
    return columns(bars, title="توازن کلاس‌ها", height=260)
