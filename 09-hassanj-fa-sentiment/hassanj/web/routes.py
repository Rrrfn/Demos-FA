# -*- coding: utf-8 -*-
"""مسیرهای صفحه‌ها — شش صفحهٔ محصول.

تحلیل متن با ``GET`` انجام می‌شود تا نتیجه قابل اشتراک و قابل نشانه‌گذاری باشد؛
ولی چون متن در آدرس می‌نشیند، همان متن روی سرور محدود و بریده می‌شود. تحلیل
گروهی ``POST`` است چون فایل در آدرس جا نمی‌گیرد.
"""
from __future__ import annotations

from urllib.parse import quote

from flask import (Blueprint, Response, current_app, render_template, request)

from .. import services
from ..batch import BatchError
from ..config import MAX_ANALYZE_CHARS, MAX_BATCH_ROWS
from ..labels import fa_number
from ..web import presenters
from ..web.context import base_context

pages = Blueprint("pages", __name__)


def _disposition(filename: str) -> str:
    """سرآمد ``Content-Disposition`` با نام فایل فارسی — به شکل امن.

    سرآمدهای HTTP فقط لاتین-۱ می‌پذیرند. گذاشتن نام فارسی خام در سرآمد، در
    سرور آزمون بی‌خطر است ولی روی سرور واقعی استثنای ``UnicodeEncodeError``
    هنگام نوشتن پاسخ می‌دهد و دانلود کاربر را وسط راه می‌شکند — همین یک بار
    با یک فایل واقعی روی سرور زنده دیده شد.

    دو نام می‌دهیم: یک نام لاتین ساده برای کلاینت‌های قدیمی و یک نام فارسی
    درصدگذاری‌شده به شکل RFC 5987 که مرورگرهای امروزی می‌خوانند.
    """
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"hassanj-analysis.csv\"; filename*=UTF-8''{encoded}"


@pages.get("/")
def overview():
    context = base_context("overview", "نمای کلی")
    context.update({
        "numbers": presenters.overview_numbers(),
        "ranking": presenters.model_ranking(),
        "balance_chart": presenters.balance_chart(),
        "class_legend": presenters.class_legend(),
        "mix_table": presenters.mix_table(),
    })
    return render_template("overview.html", **context)


@pages.get("/analyze")
def analyze():
    raw = request.args.get("q", "")
    result = services.analyse_text(raw) if raw.strip() else None
    context = base_context("analyze", "تحلیل متن")
    context.update({
        "raw": raw[:MAX_ANALYZE_CHARS],
        "max_chars": MAX_ANALYZE_CHARS,
        "max_chars_fa": fa_number(MAX_ANALYZE_CHARS),
        "view": presenters.analyze_view(result) if result else None,
        "examples": EXAMPLES,
    })
    return render_template("analyze.html", **context)


#: نمونه‌های آماده برای یک کلیک. عمداً متنوع‌اند: یک مثبت ساده، یک منفی، یک
#: خنثی، یک ایموجی‌محور، و یکی که عمداً بیرون از واژگان مدل است تا کاربرد
#: «چه وقتی مدل نمی‌داند» بلافاصله دیده شود.
EXAMPLES = (
    {"label": "مثبت", "text": "کیفیت فوق‌العاده بود و ارسال سریع، حتما دوباره می‌خرم 👍"},
    {"label": "منفی", "text": "دو هفته طول کشید و بسته پاره رسید، اصلا راضی نیستم"},
    {"label": "خنثی", "text": "بسته رسید، باید چند روز استفاده کنم بعد نظر بدم"},
    {"label": "مرکب", "text": "بد نبود، حتی می‌تونم بگم خوب هم بود"},
    {"label": "فقط ایموجی", "text": "❤️💯"},
    {"label": "خارج از دامنه", "text": "The delivery took longer than the estimate but overall acceptable"},
)


@pages.route("/batch", methods=["GET", "POST"])
def batch():
    context = base_context("batch", "تحلیل گروهی")
    context.update({
        "max_rows": fa_number(MAX_BATCH_ROWS),
        "max_rows_raw": MAX_BATCH_ROWS,
        "outcome": None,
        "error": None,
    })
    if request.method == "GET":
        return render_template("batch.html", **context)

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        context["error"] = "فایلی انتخاب نشده است."
        return render_template("batch.html", **context), 400

    try:
        outcome = services.analyse_table(upload.read())
    except BatchError as error:
        context["error"] = str(error)
        return render_template("batch.html", **context), 400
    except Exception:                      # noqa: BLE001
        current_app.logger.exception("تحلیل گروهی شکست خورد")
        context["error"] = ("پردازش فایل ممکن نشد. اگر فایل بزرگ است، آن را به "
                            "قطعه‌های کوچک‌تر تقسیم کنید.")
        return render_template("batch.html", **context), 500

    if request.form.get("action") == "download":
        from .. import batch as batch_module

        payload, filename = batch_module.to_csv_bytes(outcome["results"],
                                                       upload.filename)
        #: ``charset`` عمداً داخل mimetype نوشته نمی‌شود؛ Flask خودش اضافه‌اش
        #: می‌کند و نوشتن دوباره‌اش سرآمد را به «charset=utf-8; charset=utf-8»
        #: بدل می‌کرد.
        return Response(
            payload, mimetype="text/csv",
            headers={"Content-Disposition": _disposition(filename)})

    context.update({
        "outcome": outcome,
        "share_chart": presenters.batch_share_chart(outcome["summary"]),
        "class_legend": presenters.class_legend(),
    })
    return render_template("batch.html", **context)


@pages.get("/analytics")
def analytics_page():
    context = base_context("analytics", "تحلیل")
    context.update({
        "numbers": presenters.summary_cards(),
        "comparison_chart": presenters.mix_comparison_chart(),
        "monthly_chart": presenters.monthly_chart(),
        "confidence_chart": presenters.confidence_chart(),
        "length_chart": presenters.length_chart(),
        "coverage_chart": presenters.coverage_chart(),
        "coverage_rows": presenters.coverage_rows(),
        "mix_table": presenters.mix_table(),
        "class_legend": presenters.class_legend(),
        "terms": {code: presenters.terms_chart(code) for code in ("pos", "neg")},
    })
    return render_template("analytics.html", **context)


@pages.get("/model")
def model_page():
    context = base_context("model", "مدل")
    context.update({
        "highlights": presenters.metric_highlights(),
        "class_report": presenters.class_report_rows(),
        "ranking": presenters.model_ranking(),
        "misclassifications": presenters.misclassification_rows(),
        "hard_cases": presenters.hard_case_rows(),
        "unknown": presenters.unknown_rows(),
    })
    return render_template("model.html", **context)


@pages.get("/methodology")
def methodology():
    context = base_context("methodology", "متدولوژی")
    context.update({
        "metrics": services.metrics(),
        "class_chart": presenters.columns_chart(),
        "class_legend": presenters.class_legend(),
        #: روند اندازه‌گیری‌شده و ترکیب اعلام‌شده کنار هم می‌آیند تا تطابقشان
        #: قابل مشاهده باشد؛ اگر این دو از هم بیفتند، جایی از ساخت دیتاست
        #: مشکل دارد و همین جدول نشانش می‌دهد.
        "trend": services.monthly(),
        "declared": services.declared_trend(),
    })
    return render_template("methodology.html", **context)
