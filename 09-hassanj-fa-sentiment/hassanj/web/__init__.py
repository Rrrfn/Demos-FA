# -*- coding: utf-8 -*-
"""سازندهٔ برنامه — تنها جایی که اجزا به هم وصل می‌شوند.

ترتیب کار مهم است:

۱) برنامه با مسیر صریح ``templates`` و ``static`` ساخته می‌شود. بستهٔ ``hassanj``
   داخل خودش قالب و دارایی دارد، پس برنامه به پوشهٔ کاری جاری وابسته نیست؛ از
   هر مسیری اجرا شود همان را می‌بیند.

۲) فیلترها پیش از ثبت مسیرها می‌آیند تا قالب‌ها در زمان رندر همه را داشته باشند.

۳) مسیرهای خطا هم قالب می‌گیرند تا کاربر هرگز صفحهٔ خطای خام Flask را نبیند.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from ..config import STATIC_DIR, TEMPLATES_DIR
from . import filters as filter_module
from .api import api
from .context import base_context
from .routes import pages


def create_app(**overrides) -> Flask:
    """برنامهٔ Flask آمادهٔ سرو.

    ``**overrides`` روی پیکربندی پیش‌فرض می‌نشیند — همان چیزی که آزمون‌ها برای
    ``TESTING`` و کلید نشست استفاده می‌کنند.
    """
    app = Flask(
        __name__,
        template_folder=os.path.relpath(TEMPLATES_DIR, os.path.dirname(__file__)),
        static_folder=os.path.relpath(STATIC_DIR, os.path.dirname(__file__)),
        static_url_path="/static",
    )
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "hassanj-local-dev"),
        JSON_AS_ASCII=False,
        TEMPLATES_AUTO_RELOAD=False,
        #: نتیجهٔ تحلیل گروهی حداکثر ۵ مگابایت فایل ورودی دارد؛ سقف Flask را
        #: کمی بالاتر می‌بریم تا خطای ۴۱۳ پیش از پیام خودمان رخ ندهد.
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )
    app.config.update(overrides)

    filter_module.register(app)
    app.register_blueprint(pages)
    app.register_blueprint(api)

    _register_error_handlers(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    def wants_json() -> bool:
        return request.path.startswith("/api/")

    @app.errorhandler(404)
    def not_found(error):
        if wants_json():
            return jsonify({"ok": False, "error": "مسیر یافت نشد."}), 404
        context = base_context("", "صفحه پیدا نشد")
        return render_template("404.html", **context), 404

    @app.errorhandler(413)
    def too_large(error):
        if wants_json():
            return jsonify({"ok": False, "error": "حجم درخواست بیش از حد مجاز است."}), 413
        context = base_context("", "فایل بزرگ‌تر از حد مجاز")
        return render_template("413.html", **context), 413

    @app.errorhandler(500)
    def server_error(error):
        if wants_json():
            return jsonify({"ok": False, "error": "خطای داخلی سرور."}), 500
        context = base_context("", "خطای داخلی")
        return render_template("500.html", **context), 500
