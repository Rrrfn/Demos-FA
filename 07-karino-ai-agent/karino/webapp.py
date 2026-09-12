# -*- coding: utf-8 -*-
"""کارخانهٔ اپلیکیشن Flask.

ساخت اپ در یک تابع انجام می‌شود (نه در سطح ماژول) تا:

* تست‌ها بتوانند با تنظیمات و پایگاه دادهٔ موقت، اپ تازه بسازند؛
* ``gunicorn karino.webapp:app`` هم کار کند — یک ``app`` سطح ماژول برای
  سازگاری با WSGI نگه داشته شده، ولی خودش از همین کارخانه می‌آید.
"""
from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request

from .config import get_settings
from .core.errors import KarinoError
from .storage import activity, database

log = logging.getLogger("krn.webapp")


def create_app(*, bootstrap: bool = True, start_scheduler: bool | None = None,
               settings=None) -> Flask:
    """ساخت اپ. ``bootstrap`` یعنی پایگاه داده و اولین دور جمع‌آوری اجرا شود."""
    settings = settings or get_settings()
    settings.ensure_dirs()

    app = Flask(__name__, template_folder="web/templates", static_folder="static")
    app.config.update(
        SECRET_KEY=settings.admin_token or "karino-demo",
        JSON_AS_ASCII=False,
        KARINO_SETTINGS=settings,
    )

    from .web.pages import bp as pages_bp
    from .web.api import bp as api_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    _register_health(app, settings)
    _register_template_helpers(app)
    _register_context(app, settings)
    _register_error_handlers(app)

    if bootstrap:
        _bootstrap(app, settings, start_scheduler)
    return app


_bootstrapped = False


def reset_bootstrap_flag() -> None:
    """برای آزمون‌ها — تا محافظ «یک‌بار در پروسه» دوباره سنجیده شود."""
    global _bootstrapped
    _bootstrapped = False


def _bootstrap(app: Flask, settings, start_scheduler: bool | None) -> None:
    """آماده‌سازی یک‌بارهٔ پایگاه داده، دور نخست و زمان‌بند.

    محافظ در سطح *پروسه* است، نه در سطح اپ. دلیلش این است که این ماژول یک
    ``app`` سطح ماژول هم برای WSGI می‌سازد و ``python -m karino serve`` هم
    اپ خودش را؛ محافظ اپی باعث می‌شد یک اجرای توسعه دو بار پایگاه داده را
    بسازد، دو بار جمع‌آوری کند و دو ردیف «راه‌اندازی» ثبت کند.
    """
    global _bootstrapped
    state = app.extensions.setdefault("karino", {})
    if _bootstrapped:
        state["bootstrapped"] = True
        return

    database.init_db()
    activity.log("boot", "سامانه راه‌اندازی شد", level="info",
                 meta={"env": settings.env})

    if settings.collect_on_boot:
        from .services.ingest import run_ingest, score_pending

        try:
            stats = run_ingest(settings=settings)
            state["last_ingest"] = stats
        except Exception as exc:  # noqa: BLE001 — راه‌اندازی هرگز نباید بشکند
            log.exception("boot ingest failed")
            activity.log("ingest_error", f"دور نخست جمع‌آوری شکست خورد — {exc}",
                         level="error")
        score_pending()

    should_schedule = settings.enable_scheduler if start_scheduler is None else start_scheduler
    if should_schedule:
        from .scheduler import start as start_scheduler_fn

        try:
            start_scheduler_fn(settings)
            state["scheduler"] = True
        except Exception as exc:  # noqa: BLE001
            log.exception("scheduler start failed")
            activity.log("scheduler_error", f"زمان‌بند شروع نشد — {exc}", level="warning")

    _bootstrapped = True
    state["bootstrapped"] = True


def _register_health(app: Flask, settings) -> None:
    """``/health`` بیرون از پیشوند نسخه و بدون پوشش — قرارداد سامانهٔ پایش میزبان."""

    @app.get("/health")
    def _health():
        from .pipeline.scoring import BUDGETS
        from .services.ingest import known_sources
        from .storage import database, jobs as jobs_repo

        db_ok = True
        try:
            database.init_db()
            total = jobs_repo.count()
        except Exception:  # noqa: BLE001
            db_ok, total = False, 0

        return jsonify({
            "status": "ok" if db_ok else "degraded",
            "service": "karino-ai-agent",
            "version": app.config.get("KARINO_VERSION", "1.0"),
            "env": settings.env,
            "database": "ok" if db_ok else "unavailable",
            "jobs": total,
            "sources": len(known_sources()),
            "score_budget": sum(BUDGETS.values()),
        })


def _register_context(app: Flask, settings) -> None:
    """متغیرهای مشترک همهٔ قالب‌ها — قالب نباید به ``settings`` دسترسی مستقیم داشته باشد."""
    from flask import request

    @app.context_processor
    def _common():
        return {
            "settings": settings,
            "app_version": app.config.get("KARINO_VERSION", "1.0"),
            "banner": None,
            "search_value": (request.args.get("q") or "")[:120],
        }


def _register_template_helpers(app: Flask) -> None:
    """فیلترهای نمایش فارسی — قالب‌ها عدد خام لاتین نشان نمی‌دهند."""
    from .core.models import ENGAGEMENT_LABELS, SENIORITY_LABELS
    from .core.text import (fa_delta, fa_digits, fa_number, freshness_band,
                            relative_time)
    from .pipeline.scoring import verdict_label
    from .web.presentation import env_label, kind_label, meta_pairs

    app.jinja_env.filters.update({
        "fa": fa_number,
        "fa_digits": fa_digits,
        "fa_delta": fa_delta,
        "timeago": relative_time,
        "freshness": freshness_band,
        "verdict": verdict_label,
        "seniority": lambda value: SENIORITY_LABELS.get(value, value or "نامشخص"),
        "engagement": lambda value: ENGAGEMENT_LABELS.get(value, value or "نامشخص"),
        # رویدادها شناسه و کلید انگلیسی دارند؛ رابط هرگز خام نشانشان نمی‌دهد.
        "kind_label": kind_label,
        "meta_pairs": meta_pairs,
        "env_label": env_label,
    })
    app.jinja_env.globals.update({
        "fa_number": fa_number,
        "relative_time": relative_time,
        "score_band": _score_band,
    })


def _score_band(total) -> str:
    """دستهٔ رنگی امتیاز برای رابط — تنها جای تعریف آستانه‌ها."""
    if total is None or total < 0:
        return "none"
    if total >= 85:
        return "excellent"
    if total >= 72:
        return "strong"
    if total >= 55:
        return "moderate"
    return "weak"


def _register_error_handlers(app: Flask) -> None:
    """همهٔ خطاها یک قالب پاسخ یکدست می‌گیرند — برای API و صفحات."""

    @app.errorhandler(KarinoError)
    def _domain_error(exc: KarinoError):
        if _wants_json():
            return jsonify({"ok": False, "error": exc.to_dict()}), exc.status
        return render_template("error.html", error=exc.to_dict()), exc.status

    @app.errorhandler(404)
    def _not_found(_):
        if _wants_json():
            return jsonify({"ok": False, "error": {
                "code": "not_found", "message": "مسیر یا مورد درخواستی پیدا نشد."}}), 404
        return render_template("error.html", error={
            "code": "not_found", "message": "مسیر یا مورد درخواستی پیدا نشد."}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_):
        return jsonify({"ok": False, "error": {
            "code": "method_not_allowed",
            "message": "متد درخواست برای این مسیر مجاز نیست."}}), 405

    @app.errorhandler(500)
    def _server_error(exc):
        log.exception("unhandled error")
        if _wants_json():
            return jsonify({"ok": False, "error": {
                "code": "internal_error", "message": "خطای داخلی رخ داد."}}), 500
        return render_template("error.html", error={
            "code": "internal_error", "message": "خطای داخلی رخ داد."}), 500


def _wants_json() -> bool:
    """آیا این درخواست پاسخ جیسون می‌خواهد؟ (مسیر API یا هدر Accept)"""
    if request.path.startswith("/api/"):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


# سازگاری با WSGI: gunicorn karino.webapp:app
app = create_app()


__all__ = ["app", "create_app"]
