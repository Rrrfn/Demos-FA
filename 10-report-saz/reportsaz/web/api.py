# -*- coding: utf-8 -*-
"""API استاندارد JSON.

پاسخ همهٔ endpointها یک شکل دارد تا مصرف‌کنندهٔ ماشینی به شرط‌نویسی نیفتد:

    {"ok": true,  "data": {...}}
    {"ok": false, "error": {"code": "...", "message": "...", "detail": ""}}

کد وضعیت هم درست برگردانده می‌شود (۴۰۰ برای ورودی نامعتبر، ۴۰۴ برای بستهٔ
ناموجود، ۴۱۳ برای فایل بزرگ). پیش از این نسخه، خطای ورودی «۲۰۰ با پیام خطا»
برمی‌گشت و مصرف‌کننده نمی‌فهمید موفق بوده یا نه.
"""
from __future__ import annotations

import io

from flask import Blueprint, jsonify, request, send_file

from ..cleaning import CleanOptions
from ..config import MAX_UPLOAD_MB, QUALITY_METHOD, theme_names
from ..errors import ReportSazError
from ..export_excel import build_workbook
from ..export_pdf import build_pdf
from ..profile import pick_dimensions, pick_metrics
from ..report import build_report
from . import context as ctx
from . import presenters as view

bp = Blueprint("api", __name__, url_prefix="/api")


def _ok(payload: dict, status: int = 200):
    return jsonify({"ok": True, "data": payload}), status


def _fail(code: str, message: str, status: int = 400, detail: str = ""):
    return jsonify({"ok": False, "error": {"code": code, "message": message,
                                           "detail": detail}}), status


def _body() -> dict:
    """بدنهٔ JSON درخواست — اگر بدنه نبود یا خراب بود، دیکشنری خالی."""
    return request.get_json(silent=True) or {}


# ------------------------------------------------------------------ ها
@bp.get("")
def index():
    """فهرست endpointها — خودمستند، بدون نیاز به خواندن کد."""
    return _ok({
        "service": "report-saz",
        "endpoints": [
            {"method": "POST", "path": "/api/upload",
             "body": "multipart/form-data با کلید file",
             "returns": "شناسهٔ بسته و پروفایل اولیه"},
            {"method": "GET", "path": "/api/dataset/<id>",
             "returns": "فراداده و گام جاری بسته"},
            {"method": "GET", "path": "/api/profile/<id>",
             "returns": "پروفایل ستون‌ها و امتیاز کیفیت"},
            {"method": "POST", "path": "/api/clean/<id>",
             "body": "{\"options\": {\"drop_duplicates\": true, ...}}",
             "returns": "مسائل و اصلاحات اعمال‌شده"},
            {"method": "POST", "path": "/api/analyze/<id>",
             "body": "{\"metric\": \"...\", \"dimension\": \"...\", \"date\": \"...\"}",
             "returns": "شاخص‌ها، بینش‌ها، سری‌ها و ناهنجاری‌ها"},
            {"method": "GET", "path": "/api/report/<id>",
             "returns": "ساختار کامل گزارش"},
            {"method": "GET", "path": "/api/export/<id>/excel",
             "returns": "فایل xlsx"},
            {"method": "GET", "path": "/api/export/<id>/pdf",
             "returns": "فایل pdf"},
            {"method": "GET", "path": "/health", "returns": "وضعیت سرویس"},
        ],
        "limits": {"max_upload_mb": MAX_UPLOAD_MB,
                   "themes": theme_names()},
        "quality_method": QUALITY_METHOD,
    })


@bp.post("/upload")
def upload():
    """بارگذاری فایل و اجرای گام بازرسی."""
    uploaded = request.files.get("file")
    if uploaded is None or not (uploaded.filename or "").strip():
        return _fail("missing_file",
                     "فایلی در درخواست نبود. کلید فایل باید «file» باشد.")
    bundle = ctx.create_bundle(uploaded)
    ctx.run_inspect(bundle)
    meta = bundle.meta
    return _ok({
        "dataset_id": bundle.dataset_id,
        "stage": meta.get("stage"),
        "display_name": meta.get("display_name"),
        "size_bytes": meta.get("size_bytes"),
        "extension": meta.get("extension"),
        "warnings": meta.get("warnings", []),
        "read": meta.get("read", {}),
        "links": _links(bundle.dataset_id),
    }, 201)


@bp.get("/dataset/<dataset_id>")
def dataset(dataset_id: str):
    """فرادادهٔ بسته — بدون دادهٔ جدول."""
    bundle = ctx.open_bundle(dataset_id)
    meta = bundle.meta
    return _ok({
        "dataset_id": bundle.dataset_id,
        "stage": meta.get("stage"),
        "display_name": meta.get("display_name"),
        "extension": meta.get("extension"),
        "size_bytes": meta.get("size_bytes"),
        "created_at": meta.get("created_at"),
        "theme": meta.get("theme", "corporate"),
        "warnings": meta.get("warnings", []),
        "read": meta.get("read", {}),
        "has_analysis": bool(meta.get("analysis")),
        "links": _links(bundle.dataset_id),
    })


@bp.get("/profile/<dataset_id>")
def profile(dataset_id: str):
    """پروفایل کامل ستون‌ها، امتیاز کیفیت و مسائل."""
    bundle = ctx.open_bundle(dataset_id)
    if not bundle.reached(ctx.STAGE_INSPECTED):
        ctx.run_inspect(bundle)
    payload = bundle.meta.get("profile") or {}
    payload["findings"] = bundle.meta.get("findings", [])
    payload["read"] = bundle.meta.get("read", {})
    payload["quality_method"] = QUALITY_METHOD
    payload["suggested"] = {
        "metrics": pick_metrics(bundle.profile()) if bundle.profile() else [],
        "dimensions": pick_dimensions(bundle.profile()) if bundle.profile() else [],
    }
    return _ok(payload)


@bp.post("/clean/<dataset_id>")
def clean_endpoint(dataset_id: str):
    """اعمال پاک‌سازی با گزینه‌های داده‌شده."""
    bundle = ctx.open_bundle(dataset_id)
    payload = _body()
    options = CleanOptions.from_payload(payload.get("options") or {})
    result = ctx.run_clean(bundle, options)
    return _ok({"cleaning": result.as_dict(), "options": options.as_dict(),
                "profile": bundle.meta.get("profile", {})})


@bp.post("/analyze/<dataset_id>")
def analyze(dataset_id: str):
    """اجرای تحلیل و برگرداندن نتیجهٔ کامل."""
    bundle = ctx.open_bundle(dataset_id)
    payload = _body()
    analysis = ctx.run_analyze(
        bundle, metric=str(payload.get("metric") or "").strip(),
        dimension=str(payload.get("dimension") or "").strip(),
        date_column=str(payload.get("date") or "").strip())
    return _ok(analysis.as_dict())


@bp.get("/report/<dataset_id>")
def report(dataset_id: str):
    """ساختار کامل گزارش — همان چیزی که PDF و HTML از آن ساخته می‌شوند."""
    bundle = ctx.open_bundle(dataset_id)
    if bundle.analysis() is None:
        ctx.run_analyze(bundle)
    built = _build(bundle)
    return _ok(built.as_dict())


@bp.post("/theme/<dataset_id>")
def set_theme(dataset_id: str):
    """تغییر تم گزارش."""
    bundle = ctx.open_bundle(dataset_id)
    name = str(_body().get("theme") or "").strip()
    if name not in theme_names():
        return _fail("unknown_theme",
                     "تم انتخاب‌شده شناخته نمی‌شود. یکی از تم‌های فهرست را "
                     "انتخاب کنید.")
    ctx.set_theme(bundle, name)
    return _ok({"theme": name})


@bp.get("/export/<dataset_id>/excel")
def export_excel(dataset_id: str):
    """خروجی اکسل."""
    bundle = ctx.open_bundle(dataset_id)
    if bundle.analysis() is None:
        ctx.run_analyze(bundle)
    payload = build_workbook(_build(bundle), analysis=bundle.analysis(),
                             clean=bundle.clean_result(),
                             frame=bundle.working_frame())
    return send_file(
        io.BytesIO(payload), as_attachment=True,
        download_name=f"report-{dataset_id}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")


@bp.get("/export/<dataset_id>/pdf")
def export_pdf(dataset_id: str):
    """خروجی PDF."""
    bundle = ctx.open_bundle(dataset_id)
    if bundle.analysis() is None:
        ctx.run_analyze(bundle)
    payload = build_pdf(_build(bundle), analysis=bundle.analysis(),
                        frame=bundle.working_frame())
    return send_file(io.BytesIO(payload), as_attachment=True,
                     download_name=f"report-{dataset_id}.pdf",
                     mimetype="application/pdf")


def _build(bundle: ctx.Bundle):
    """گزارش کامل — مشترک بین endpointها."""
    charts = {key: item["svg"]
              for key, item in view.render_charts(bundle.analysis(),
                                                  bundle).items()
              if not item.get("empty")}
    meta = ctx.report_meta(bundle)
    return build_report(
        title=f"گزارش تحلیلی — {meta['display_name']}",
        subtitle="تحلیل خودکار داده و کیفیت آن",
        meta=meta, profile=bundle.profile(), analysis=bundle.analysis(),
        clean=bundle.clean_result(), theme_name=meta["theme"],
        svg_charts=charts)


def _links(dataset_id: str) -> dict:
    """نشانی گام‌های بعدی — مصرف‌کنندهٔ API لازم نباشد نشانی بسازد."""
    return {
        "profile": f"/api/profile/{dataset_id}",
        "clean": f"/api/clean/{dataset_id}",
        "analyze": f"/api/analyze/{dataset_id}",
        "report": f"/api/report/{dataset_id}",
        "excel": f"/api/export/{dataset_id}/excel",
        "pdf": f"/api/export/{dataset_id}/pdf",
        "pages": {
            "inspect": f"/dataset/{dataset_id}/inspect",
            "clean": f"/dataset/{dataset_id}/clean",
            "dashboard": f"/dataset/{dataset_id}/dashboard",
            "report": f"/dataset/{dataset_id}/report",
        },
    }
