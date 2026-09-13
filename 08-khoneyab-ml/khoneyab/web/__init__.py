# -*- coding: utf-8 -*-
"""کارخانهٔ برنامهٔ وب — ساخت، پیکربندی و سیم‌کشی.

مرزهای برنامه اینجا بسته می‌شود: مسیرها، فیلترهای قالب، کلید نشست، سرصفحه‌های
کش، و صفحه‌های خطا. هیچ منطق دامنه‌ای در این بسته نیست؛ محاسبات در
``khoneyab`` می‌ماند و این لایه فقط آن را به HTML و JSON تبدیل می‌کند.
"""
from __future__ import annotations

import os
import time

from flask import Flask, render_template

from ..config import STATIC_DIR, TEMPLATES_DIR

#: ثانیهٔ کش برای دارایی‌های ایستا. عکس‌ها و قلم‌ها تغییر نمی‌کنند و نامشان
#: نسخه‌دار است، پس می‌توان با خیال راحت یک ماه کش کرد.
STATIC_MAX_AGE = 60 * 60 * 24 * 30

#: کلید پیش‌فرض توسعه. در استقرار باید ``SECRET_KEY`` تعیین شود، وگرنه هر
#: راه‌اندازی دوباره نشست‌ها را بی‌اعتبار می‌کند.
DEV_SECRET = "khoneyab-development-key-not-for-deployment"


def create_app(**overrides) -> Flask:
    """ساخت برنامه. ورودی‌های اختیاری روی پیکربندی پیش‌فرض می‌نشینند."""
    app = Flask(
        __name__,
        static_folder=STATIC_DIR,
        template_folder=TEMPLATES_DIR,
        static_url_path="/static",
    )
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", DEV_SECRET),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
        SEND_FILE_MAX_AGE_DEFAULT=STATIC_MAX_AGE,
        JSON_AS_ASCII=False,
        TEMPLATES_AUTO_RELOAD=False,
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    app.config.update(overrides)

    from . import filters
    filters.register(app)

    from .api import bp as api_bp
    from .routes import bp as pages_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)

    _register_error_pages(app)
    _register_headers(app)
    return app


def _register_headers(app: Flask) -> None:
    """سرصفحه‌های امنیتی و کش برای دارایی‌های ایستا."""

    @app.after_request
    def _headers(response):
        if response.status_code < 400:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
        return response


def _register_error_pages(app: Flask) -> None:
    """صفحه‌های خطا با همان پوستهٔ سایت، نه صفحهٔ پیش‌فرض وبه‌سرور.

    این صفحه‌ها هم ``base.html`` را می‌کشند، پس همان متغیرهای پایه را لازم
    دارند؛ بدون آن‌ها خودِ صفحهٔ خطا خطا می‌دهد و کاربر دست خالی می‌ماند.
    """
    from .context import shell

    @app.errorhandler(404)
    def _not_found(error):
        return render_template("404.html", **shell("")), 404

    @app.errorhandler(500)
    def _server_error(error):  # pragma: no cover - فقط در خطای واقعی
        return render_template("500.html", **shell("")), 500


#: زمان آغاز پروسه — برای گزارش در ``/health``.
STARTED_AT = time.time()
