# -*- coding: utf-8 -*-
"""مسیرهای صفحه — گردش کار پنج‌گامی محصول.

هر گام یک نشانی مستقل دارد تا کاربر بتواند بین گام‌ها جابه‌جا شود، صفحه را
نشانه‌گذاری کند و به عقب برگردد. اگر همه در یک درخواست انجام می‌شد، کاربر به
گزارش نهایی پرت می‌شد و نمی‌فهمید در داده‌اش چه اتفاقی افتاده.
"""
from __future__ import annotations

import io
import logging

from flask import (Blueprint, redirect, render_template, request, send_file,
                   url_for)

from ..cleaning import CleanOptions
from ..config import QUALITY_METHOD, theme_names
from ..demo import build_demo_workbook, demo_description
from ..errors import DatasetNotFoundError, ReportSazError
from ..export_excel import build_workbook
from ..export_pdf import build_pdf
from ..report import build_report
from . import context as ctx
from . import presenters as view

bp = Blueprint("pages", __name__)
logger = logging.getLogger("reportsaz")


# ------------------------------------------------------------------ خانه
@bp.get("/")
def landing():
    """صفحهٔ خانه — محصول، گردش کار، قابلیت‌ها و ضمانت‌ها."""
    return render_template("landing.html", title="گزارش‌ساز",
                           view=view.landing_view(demo_description()))


@bp.get("/methodology")
def methodology():
    """روش کار — امتیاز کیفیت، تشخیص نوع، ناهنجاری و محدودیت‌ها."""
    return render_template("methodology.html", title="روش کار",
                           quality_method=QUALITY_METHOD,
                           weights=[{"label": label, "value": value}
                                    for label, value in
                                    {"کامل‌بودن": 0.35, "اعتبار": 0.25,
                                     "یکتایی": 0.20, "یکدستی": 0.20}.items()])


@bp.get("/health")
def health():
    """بررسی سلامت سرویس — برای Render و پایش."""
    from flask import jsonify

    from ..store import sweep, usage

    swept = sweep()
    return jsonify({
        "status": "ok",
        "service": "report-saz",
        "version": _version(),
        "storage": usage(),
        "swept": swept,
    })


@bp.get("/demo")
def demo():
    """دانلود مجموعهٔ دادهٔ نمونه — تا کارفرما بی‌درنگ امتحان کند."""
    payload = build_demo_workbook()
    return send_file(
        io.BytesIO(payload), as_attachment=True,
        download_name="sample-sales.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")


# ------------------------------------------------------------------ بارگذاری
@bp.post("/upload")
def upload():
    """دریافت فایل و اجرای گام بازرسی."""
    uploaded = request.files.get("file")
    if uploaded is None or not (uploaded.filename or "").strip():
        raise ReportSazError(
            "فایلی انتخاب نشده است. یک فایل XLSX یا CSV بفرستید.")
    bundle = ctx.create_bundle(uploaded)
    ctx.run_inspect(bundle)
    return redirect(url_for("pages.inspect", dataset_id=bundle.dataset_id))


@bp.get("/dataset/<dataset_id>")
def open_dataset(dataset_id: str):
    """هدایت به گام جاری بسته."""
    bundle = ctx.open_bundle(dataset_id)
    stage = bundle.stage()
    if stage == ctx.STAGE_ANALYSED:
        return redirect(url_for("pages.dashboard", dataset_id=dataset_id))
    if stage == ctx.STAGE_CLEANED:
        return redirect(url_for("pages.clean", dataset_id=dataset_id))
    return redirect(url_for("pages.inspect", dataset_id=dataset_id))


# ------------------------------------------------------------------ بازرسی
@bp.get("/dataset/<dataset_id>/inspect")
def inspect(dataset_id: str):
    """گام بازرسی — پروفایل کامل پیش از هر تغییری."""
    bundle = ctx.open_bundle(dataset_id)
    if not bundle.reached(ctx.STAGE_INSPECTED):
        ctx.run_inspect(bundle)
    profile = bundle.profile()
    if profile is None:
        raise DatasetNotFoundError(
            "پروفایل این بسته ساخته نشد؛ فایل را دوباره بارگذاری کنید.")
    return render_template(
        "inspect.html", title="بازرسی داده",
        rail=view.stage_rail(bundle, ctx.STAGE_INSPECTED),
        view=view.inspect_view(bundle, profile, bundle.meta.get("read") or {},
                               bundle.meta.get("findings") or []),
        meta=view.meta_view(bundle))


# ------------------------------------------------------------------ پاک‌سازی
@bp.route("/dataset/<dataset_id>/clean", methods=["GET", "POST"])
def clean_page(dataset_id: str):
    """گام پاک‌سازی — مسائل، گزینه‌ها و اصلاحات اعمال‌شده."""
    bundle = ctx.open_bundle(dataset_id)
    if not bundle.reached(ctx.STAGE_INSPECTED):
        ctx.run_inspect(bundle)

    if request.method == "POST":
        #: گزینه‌ها از فرم می‌آیند؛ نبودِ هر کلید یعنی خاموش، چون کاربر
        #: تیکِ آن را برداشته است.
        payload = {item["key"]: (item["key"] in request.form)
                   for item in _option_keys()}
        options = CleanOptions.from_payload(payload)
        ctx.run_clean(bundle, options)
        return redirect(url_for("pages.clean_page", dataset_id=dataset_id))

    options = CleanOptions.from_payload(
        {item["key"]: True for item in _option_keys()})
    result = bundle.clean_result() if bundle.reached(ctx.STAGE_CLEANED) else None
    return render_template(
        "clean.html", title="پاک‌سازی داده",
        rail=view.stage_rail(bundle, ctx.STAGE_CLEANED),
        view=view.clean_view(bundle, bundle.profile(), options, result),
        meta=view.meta_view(bundle))


def _option_keys() -> list[dict]:
    from ..cleaning import options_meta

    return options_meta()


# ------------------------------------------------------------------ تحلیل
@bp.get("/dataset/<dataset_id>/dashboard")
def dashboard(dataset_id: str):
    """گام تحلیل — شاخص‌ها، بینش‌ها و نمودارها."""
    bundle = ctx.open_bundle(dataset_id)
    _ensure_analysis(bundle)
    profile = bundle.profile()
    analysis = bundle.analysis()
    if profile is None or analysis is None:
        raise DatasetNotFoundError(
            "نتیجهٔ تحلیل در دسترس نیست؛ فایل را دوباره بارگذاری کنید.")
    return render_template(
        "dashboard.html", title="تحلیل داده",
        rail=view.stage_rail(bundle, ctx.STAGE_ANALYSED),
        view=view.dashboard_view(bundle, profile, analysis),
        meta=view.meta_view(bundle))


@bp.post("/dataset/<dataset_id>/analyze")
def analyze(dataset_id: str):
    """انتخاب دستی محورهای تحلیل و اجرای دوباره."""
    bundle = ctx.open_bundle(dataset_id)
    ctx.run_analyze(
        bundle,
        metric=(request.form.get("metric") or "").strip(),
        dimension=(request.form.get("dimension") or "").strip(),
        date_column=(request.form.get("date") or "").strip(),
    )
    return redirect(url_for("pages.dashboard", dataset_id=dataset_id))


def _ensure_analysis(bundle: ctx.Bundle) -> None:
    """تحلیل را اگر ساخته نشده می‌سازد."""
    if bundle.analysis() is not None:
        return
    if not bundle.reached(ctx.STAGE_CLEANED):
        ctx.run_clean(bundle, CleanOptions.from_payload(
            {item["key"]: True for item in _option_keys()}))
    ctx.run_analyze(bundle)


@bp.post("/dataset/<dataset_id>/theme")
def set_theme(dataset_id: str):
    """انتخاب تم گزارش و بازگشت به همان صفحه."""
    bundle = ctx.open_bundle(dataset_id)
    name = (request.form.get("theme") or "").strip()
    if name not in theme_names():
        raise ReportSazError(
            "تم انتخاب‌شده شناخته نمی‌شود. یکی از تم‌های فهرست را انتخاب کنید.")
    ctx.set_theme(bundle, name)
    target = (request.form.get("next") or "").strip()
    if target == "report":
        return redirect(url_for("pages.report", dataset_id=dataset_id))
    if target == "dashboard":
        return redirect(url_for("pages.dashboard", dataset_id=dataset_id))
    return redirect(url_for("pages.report", dataset_id=dataset_id))


# ------------------------------------------------------------------ گزارش
@bp.get("/dataset/<dataset_id>/report")
def report(dataset_id: str):
    """پیش‌نمایش گزارش — همان ساختاری که در PDF می‌آید."""
    bundle = ctx.open_bundle(dataset_id)
    _ensure_analysis(bundle)
    built = _build_report(bundle)
    return render_template(
        "report.html", title="گزارش",
        rail=view.stage_rail(bundle, "reported"),
        view=view.report_view(bundle, built, bundle.analysis()),
        meta=view.meta_view(bundle))


def _build_report(bundle: ctx.Bundle):
    """ساخت گزارش کامل — مشترک بین پیش‌نمایش، PDF و اکسل."""
    profile = bundle.profile()
    analysis = bundle.analysis()
    if profile is None or analysis is None:
        raise DatasetNotFoundError(
            "برای ساخت گزارش، تحلیل باید کامل شده باشد.")
    charts = {key: item["svg"]
              for key, item in view.render_charts(analysis, bundle).items()
              if not item.get("empty")}
    meta = ctx.report_meta(bundle)
    return build_report(
        title=f"گزارش تحلیلی — {meta['display_name']}",
        subtitle="تحلیل خودکار داده و کیفیت آن",
        meta=meta, profile=profile, analysis=analysis,
        clean=bundle.clean_result(), theme_name=meta["theme"],
        svg_charts=charts)


@bp.get("/dataset/<dataset_id>/export/pdf")
def export_pdf(dataset_id: str):
    """خروجی PDF گزارش."""
    bundle = ctx.open_bundle(dataset_id)
    _ensure_analysis(bundle)
    built = _build_report(bundle)
    payload = build_pdf(built, analysis=bundle.analysis(),
                        frame=bundle.working_frame())
    logger.info("PDF ساخته شد برای بستهٔ %s (%d بایت)",
                dataset_id, len(payload))
    return send_file(io.BytesIO(payload), as_attachment=True,
                     download_name=_ascii_filename(bundle, "report.pdf"),
                     mimetype="application/pdf")


@bp.get("/dataset/<dataset_id>/export/excel")
def export_excel(dataset_id: str):
    """خروجی اکسل گزارش."""
    bundle = ctx.open_bundle(dataset_id)
    _ensure_analysis(bundle)
    built = _build_report(bundle)
    payload = build_workbook(built, analysis=bundle.analysis(),
                             clean=bundle.clean_result(),
                             frame=bundle.working_frame())
    logger.info("اکسل ساخته شد برای بستهٔ %s (%d بایت)", dataset_id, len(payload))
    return send_file(
        io.BytesIO(payload), as_attachment=True,
        download_name=_ascii_filename(bundle, "report.xlsx"),
        mimetype="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")


def _ascii_filename(bundle: ctx.Bundle, fallback: str) -> str:
    """نام فایل خروجی: پیشوند شناسه + نام امن.

    نام فارسی در سرآمد ``Content-Disposition`` مجاز نیست؛ Werkzeug خودش
    درصدگذاری UTF-8 می‌کند ولی نام لاتین جانشین هم می‌گذارد تا کارخواه‌های
    قدیمی خطا نگیرند.
    """
    extension = fallback.rsplit(".", 1)[-1]
    return f"report-{bundle.dataset_id}.{extension}"


def _version() -> str:
    from .. import __version__

    return __version__
