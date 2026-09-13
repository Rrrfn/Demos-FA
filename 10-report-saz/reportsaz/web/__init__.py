# -*- coding: utf-8 -*-
"""لایهٔ وب — کارخانهٔ برنامه و اتصال مسیرها.

ساخت برنامه در یک تابع (نه در سطح ماژول) انجام می‌شود تا آزمون بتواند چند
نمونهٔ مستقل با تنظیمات متفاوت بسازد و به وضعیت جهانی وابسته نباشد. تنها
جایی که یک نمونهٔ آماده ساخته می‌شود ``webapp.py`` است که سرور WSGI آن را
می‌خواند.
"""
from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, render_template, request

from ..config import (MAX_UPLOAD_BYTES, SERVICE_NAME, SERVICE_TAGLINE,
                      STATIC_DIR, TEMPLATES_DIR)
from ..errors import ReportSazError
from .filters import register_filters


def create_app(*, testing: bool = False) -> Flask:
    """ساخت برنامهٔ Flask با تنظیمات کامل."""
    app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
    app.config.update(
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
        JSON_AS_ASCII=False,
        TESTING=testing,
        PROPAGATE_EXCEPTIONS=testing,
    )
    app.config["SERVICE_NAME"] = SERVICE_NAME
    app.config["SERVICE_TAGLINE"] = SERVICE_TAGLINE
    app.secret_key = os.environ.get("SECRET_KEY", "report-saz-local-dev")

    register_filters(app)

    from . import api, routes
    app.register_blueprint(routes.bp)
    app.register_blueprint(api.bp)

    _register_error_handlers(app)
    _register_context(app)

    if not testing:
        logging.getLogger("reportsaz").setLevel(logging.INFO)
    return app


def _register_context(app: Flask) -> None:
    """متغیرهای مشترک همهٔ قالب‌ها.

    سقف حجم در فرم بارگذاری هم لازم است تا پیش از فرستادن فایل به سرور
    بررسی شود؛ فرستادن یک فایل ۲۰ مگابایتی و بعد شنیدن «زیاد است» تجربهٔ
    بدی است.
    """

    @app.context_processor
    def _inject():
        return {
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "service_name": SERVICE_NAME,
            "service_tagline": SERVICE_TAGLINE,
        }


def _register_error_handlers(app: Flask) -> None:
    """خطای کاربر با خطای برنامه قاطی نمی‌شود.

    خطای کاربرمحور پیام خودش را می‌گیرد و کد وضعیت درست؛ خطای واقعی در لاگ با
    رد کامل ثبت می‌شود و کاربر فقط یک پیام کوتاه می‌بیند. بدون این تفکیک، یک
    فایل خراب هم «خطای داخلی سرور» می‌شود و رفعش ناممکن است.
    """
    logger = logging.getLogger("reportsaz")

    @app.errorhandler(ReportSazError)
    def _user_error(error: ReportSazError):
        if _wants_json():
            return jsonify({"ok": False, "error": error.as_dict()}), error.status
        return render_template("error.html", error=error,
                               title="خطا"), error.status

    @app.errorhandler(413)
    def _too_large(_error):
        limit = MAX_UPLOAD_BYTES // (1024 * 1024)
        error = ReportSazError(
            f"حجم فایل بیش از حد مجاز است. سقف مجاز {limit} مگابایت است.")
        error.status = 413
        error.code = "file_too_large"
        if _wants_json():
            return jsonify({"ok": False, "error": error.as_dict()}), 413
        return render_template("error.html", error=error, title="فایل بزرگ"), 413

    @app.errorhandler(404)
    def _not_found(_error):
        message = "این نشانی در سرویس وجود ندارد."
        if _wants_json():
            return jsonify({"ok": False, "error": {"code": "not_found",
                                                   "message": message,
                                                   "detail": ""}}), 404
        return render_template("error.html", title="پیدا نشد",
                               error=ReportSazError(message)), 404

    @app.errorhandler(500)
    def _server_error(_error):
        logger.exception("خطای پیش‌بینی‌نشده در پردازش درخواست")
        message = ("پردازش این درخواست با خطای غیرمنتظره متوقف شد. فایل دوباره "
                   "بارگذاری کنید؛ اگر تکرار شد، ساختار فایل را بررسی کنید.")
        if _wants_json():
            return jsonify({"ok": False, "error": {"code": "internal",
                                                   "message": message,
                                                   "detail": ""}}), 500
        return render_template("error.html", title="خطای سرور",
                               error=ReportSazError(message)), 500

    @app.errorhandler(Exception)
    def _unhandled(error: Exception):
        #: خطاهایی که Flask خودش مدیریت می‌کند (مثل ۴۰۴) دوباره پرتاب می‌شوند.
        from werkzeug.exceptions import HTTPException

        if isinstance(error, HTTPException):
            return error
        logger.exception("خطای مدیریت‌نشده: %s", error)
        return _server_error(error)


def _wants_json() -> bool:
    """آیا پاسخ باید JSON باشد؟

    تنها مسیرهای API پاسخ JSON می‌گیرند. تصمیم‌گیری بر اساس سرآمد «پذیرش»
    اینجا غلط بود: مرورگر ``*/*`` می‌فرستد و مقایسهٔ کیفیت‌ها آن را JSON
    می‌دید، پس صفحه‌های HTML خطا هم JSON برمی‌گرداندند.
    """
    path = request.path or ""
    return path.startswith("/api") or path == "/health"
