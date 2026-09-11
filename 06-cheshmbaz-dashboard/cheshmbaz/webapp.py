# -*- coding: utf-8 -*-
"""لایهٔ وب — صفحهٔ داشبورد و API نسخه‌دار.

هر پاسخ API یک پوشش یکدست دارد:

    {"ok": true,  "data": {...}}
    {"ok": false, "error": {"code": "...", "message": "...", "field": "..."}}

هیچ endpointی استثنا بیرون نمی‌دهد: خطای دامنه به کد و پیام فارسی نگاشت
می‌شود و خطای غیرمنتظره به ۵۰۰ با همان پوشش — بدون ردپای پایتون در پاسخ.

کلید ``/api/v1`` نگه‌داشته شده تا مصرف‌کننده‌های بعدی بدون شکستن قرارداد
بتوانند به نسخهٔ بعدی بروند؛ مسیرهای بی‌نسخه هم به همین منطق وصل می‌شوند.
"""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid

from flask import Flask, Response, jsonify, render_template, request

from . import assets as registry
from .assets import ASSETS, KIND_ORDER, all_assets_ordered
from .config import Config, load_config
from .context import AppContext
from .core.errors import CheshmbazError, ValidationError
from .core.models import AlertKind, AlertStatus
from .services.collector import seed_registry

log = logging.getLogger("cheshmbaz.webapp")

OWNER_COOKIE = "cbz_owner"
DOCS = {
    "name": "Cheshmbaz Market Intelligence API",
    "version": "2.0",
    "envelope": {"ok": "bool", "data": "object", "error": "object|null"},
    "endpoints": [
        "GET  /health",
        "GET  /api/v1/meta",
        "GET  /api/v1/overview",
        "GET  /api/v1/digest",
        "GET  /api/v1/assets?kind=&page=&page_size=",
        "GET  /api/v1/assets/<slug>",
        "GET  /api/v1/assets/<slug>/series?range=1D|7D|30D|90D",
        "GET  /api/v1/movers?window=1D|7D|30D&limit=",
        "GET  /api/v1/search?q=",
        "GET  /api/v1/sources",
        "GET  /api/v1/watchlist",
        "POST /api/v1/watchlist/<slug>",
        "DELETE /api/v1/watchlist/<slug>",
        "GET  /api/v1/alerts?page=&page_size=",
        "POST /api/v1/alerts",
        "PATCH /api/v1/alerts/<id>",
        "DELETE /api/v1/alerts/<id>",
        "POST /api/v1/alerts/preview",
        "GET  /api/v1/events?slug=&page=&page_size=",
        "GET  /api/v1/status",
        "POST /api/v1/collect",
    ],
}


# --------------------------------------------------------------------- helpers
def _ok(data: dict, status: int = 200, cache_seconds: int | None = None) -> Response:
    """پاسخ موفق در پوشش یکدست."""
    response = jsonify({"ok": True, "data": data, "error": None})
    response.status_code = status
    if cache_seconds:
        response.headers["Cache-Control"] = f"private, max-age={cache_seconds}"
    return response


def _fail(code: str, message: str, status: int, field: str | None = None) -> Response:
    """پاسخ ناموفق در پوشش یکدست."""
    payload = {"code": code, "message": message}
    if field:
        payload["field"] = field
    response = jsonify({"ok": False, "data": None, "error": payload})
    response.status_code = status
    return response


def _int_arg(name: str, default: int, *, low: int, high: int) -> int:
    """خواندن عدد صحیح از کوئری با کران."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"مقدار «{name}» باید عدد باشد", name) from error
    if value < low:
        raise ValidationError(f"مقدار «{name}» کمتر از حد مجاز است", name)
    return min(value, high)


def _owner(req) -> str:
    """شناسهٔ بازدیدکننده — سربارش آدرس، وگرنه نشانهٔ کوکی."""
    header = (req.headers.get("X-Owner") or "").strip()
    if header:
        return header[:64]
    cookie = (req.cookies.get(OWNER_COOKIE) or "").strip()
    if cookie:
        return cookie[:64]
    return "public"


def _json_body() -> dict:
    """خواندن بدنهٔ JSON با خطای کنترل‌شده."""
    if not request.data:
        return {}
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("بدنهٔ JSON نامعتبر است", "body")
    if not isinstance(payload, dict):
        raise ValidationError("بدنهٔ درخواست باید یک شیء JSON باشد", "body")
    return payload


def _require_number(payload: dict, field: str, *, required: bool = True) -> float | None:
    """خواندن عدد از بدنه با اعتبارسنجی."""
    if field not in payload or payload[field] in (None, ""):
        if required:
            raise ValidationError(f"مقدار «{field}» لازم است", field)
        return None
    try:
        return float(payload[field])
    except (TypeError, ValueError) as error:
        raise ValidationError(f"مقدار «{field}» باید عدد باشد", field) from error


def _require_slug(payload: dict) -> str:
    slug = str(payload.get("slug") or "").strip()
    if not slug:
        raise ValidationError("شناسهٔ دارایی لازم است", "slug")
    if slug not in ASSETS:
        raise ValidationError(f"دارایی «{slug}» در فهرست نیست", "slug")
    return slug


def _require_kind(payload: dict) -> AlertKind:
    raw = str(payload.get("kind") or "").strip().lower()
    try:
        return AlertKind(raw)
    except ValueError as error:
        raise ValidationError(
            "نوع هشدار باید یکی از above، below یا pct_move باشد", "kind"
        ) from error


# ------------------------------------------------------------------- app factory
def create_app(context: AppContext | None = None, config: Config | None = None) -> Flask:
    """ساخت برنامهٔ Flask روی یک زمینه."""
    config = config or (context.config if context else load_config())
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.json.ensure_ascii = False
    ctx = context or AppContext.build(config)
    app.extensions["cheshmbaz"] = ctx

    # ------------------------------------------------------------ error layer
    @app.errorhandler(CheshmbazError)
    def _domain_error(error: CheshmbazError):  # noqa: ANN202
        payload = error.to_payload()
        return _fail(
            payload.get("code", "error"),
            payload.get("message", "خطا"),
            error.http_status,
            payload.get("field"),
        )

    @app.errorhandler(404)
    def _not_found(_error):  # noqa: ANN202
        return _fail("not_found", "مسیر درخواستی وجود ندارد", 404)

    @app.errorhandler(405)
    def _method_not_allowed(_error):  # noqa: ANN202
        return _fail("method_not_allowed", "متد درخواست مجاز نیست", 405)

    @app.errorhandler(sqlite3.Error)
    def _database_error(error: sqlite3.Error):  # noqa: ANN202
        log.exception("database error: %s", error)
        return _fail("storage_error", "خطا در دسترسی به داده", 500)

    @app.errorhandler(Exception)
    def _unexpected(error: Exception):  # noqa: ANN202
        log.exception("unhandled error: %s", error)
        return _fail("internal_error", "خطای داخلی سرویس", 500)

    @app.after_request
    def _identity(response: Response) -> Response:
        """نشاندن شناسهٔ بازدیدکننده برای دیده‌بان مهمان."""
        if not request.cookies.get(OWNER_COOKIE) and not request.headers.get("X-Owner"):
            response.set_cookie(
                OWNER_COOKIE, uuid.uuid4().hex[:24], max_age=31_536_000,
                samesite="Lax", httponly=False,
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    def admin_required() -> None:
        """محافظت از endpointهای تغییر وضعیت در صورت تنظیم توکن.

        وقتی توکنی پیکربندی نشده باشد دست باز است تا دموی عمومی کار کند —
        دکمهٔ «واکشی تازه» در رابط هیچ راهی برای فرستادن توکن ندارد و بستن
        همیشگی آن، دموی تولیدی را از کار می‌انداخت. به‌محض تنظیم
        ``CHESHMAZ_ADMIN_TOKEN`` همان توکن الزامی می‌شود و درخواست باید با
        هدر ``X-Admin-Token`` (یا پارامتر ``token``) بیاید.
        """
        token = ctx.config.admin_token
        if not token:
            return
        provided = request.headers.get("X-Admin-Token") or request.args.get("token") or ""
        if provided != token:
            raise ValidationError("توکن مدیر نامعتبر است", "token")

    # ------------------------------------------------------------------ views
    @app.get("/")
    def index():  # noqa: ANN202
        """صفحهٔ داشبورد — داده از API خوانده می‌شود، نه از قالب."""
        return render_template(
            "index.html",
            config={
                "environment": ctx.config.env,
                "collect_interval": ctx.config.collector.interval_seconds,
                "alert_interval": ctx.config.alerts.interval_seconds,
                "cache_seconds": ctx.config.api.cache_seconds,
                "admin_protected": bool(ctx.config.admin_token),
            },
            registry={
                "kinds": [
                    {"value": kind.value, "label": kind.label, "order": kind.order}
                    for kind in KIND_ORDER
                ],
                "assets": [
                    {"slug": a.slug, "title": a.title, "kind": a.kind.value,
                     "symbol": a.symbol, "unit": a.unit, "precision": a.precision}
                    for a in all_assets_ordered()
                ],
                "count": len(ASSETS),
            },
        )

    @app.get("/health")
    @app.get("/api/health")
    def health():  # noqa: ANN202
        """سلامت سرویس — هرگز واکشی شبکه‌ای انجام نمی‌دهد."""
        return _ok(ctx.health())

    @app.get("/api")
    @app.get("/api/v1")
    def api_index():  # noqa: ANN202
        return _ok(DOCS)

    @app.get("/api/v1/meta")
    @app.get("/api/meta")
    def meta():  # noqa: ANN202
        """فرادادهٔ رجیستری و پیکربندی — برای ساخت رابط."""
        return _ok({
            "service": "cheshmbaz-dashboard",
            "version": DOCS["version"],
            "environment": ctx.config.env,
            "kinds": [
                {"value": kind.value, "label": kind.label, "order": kind.order}
                for kind in KIND_ORDER
            ],
            "assets": [
                {
                    "slug": asset.slug, "title": asset.title, "kind": asset.kind.value,
                    "kind_label": asset.kind.label, "symbol": asset.symbol,
                    "unit": asset.unit, "unit_label": asset.unit_label,
                    "precision": asset.precision, "provider": asset.provider,
                }
                for asset in all_assets_ordered()
            ],
            "ranges": ctx.market.ranges(),
            "thresholds": {
                "live_within": ctx.config.data.live_within,
                "stale_after": ctx.config.data.stale_after,
                "expire_after": ctx.config.data.expire_after,
            },
            "intervals": {
                "collect": ctx.config.collector.interval_seconds,
                "alerts": ctx.config.alerts.interval_seconds,
            },
            "alert_kinds": [
                {"value": kind.value, "label": kind.label} for kind in AlertKind
            ],
        })

    @app.get("/api/v1/overview")
    @app.get("/api/overview")
    def overview():  # noqa: ANN202
        """نمای کلی بازار: گروه‌ها، اقلام شاخص، بیشترین تغییرها، وضعیت منابع."""
        return _ok(ctx.market.overview())

    @app.get("/api/v1/digest")
    @app.get("/api/digest")
    def digest():  # noqa: ANN202
        """خلاصهٔ سبک برای نوار بالای صفحه."""
        return _ok(ctx.market.digest())

    @app.get("/api/v1/assets")
    @app.get("/api/assets")
    def list_assets():  # noqa: ANN202
        """فهرست اقلام با فیلتر دسته و صفحه‌بندی."""
        kind_raw = (request.args.get("kind") or "").strip().lower()
        page = _int_arg("page", 1, low=1, high=10_000)
        page_size = _int_arg(
            "page_size", ctx.config.api.default_page_size,
            low=1, high=ctx.config.api.max_page_size,
        )
        selected = list(ASSETS.values())
        if kind_raw:
            if kind_raw not in {kind.value for kind in KIND_ORDER}:
                raise ValidationError("دستهٔ درخواستی معتبر نیست", "kind")
            selected = [asset for asset in all_assets_ordered() if asset.kind.value == kind_raw]

        start = (page - 1) * page_size
        window = selected[start:start + page_size]
        return _ok({
            "items": [ctx.market.card(asset.slug) for asset in window],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": len(selected),
                "pages": max(1, (len(selected) + page_size - 1) // page_size),
                "has_next": start + page_size < len(selected),
            },
        })

    @app.get("/api/v1/assets/<slug>")
    @app.get("/api/assets/<slug>")
    def asset_detail(slug: str):  # noqa: ANN202
        """جزئیات یک دارایی: کارت + پوشش تاریخچه + همهٔ بازه‌ها."""
        if slug not in ASSETS:
            registry.get(slug)  # UnknownAsset با پیام درست
        card = ctx.market.card(slug)
        card["coverage"] = ctx.storage.history.coverage(slug)
        card["ranges"] = ctx.market.ranges(slug)
        card["watchlist"] = ctx.storage.watchlist.has(_owner(request), slug)
        return _ok(card)

    @app.get("/api/v1/assets/<slug>/series")
    @app.get("/api/assets/<slug>/series")
    def asset_series(slug: str):  # noqa: ANN202
        """سری زمانی واقعی از پایگاه داده."""
        range_key = (request.args.get("range") or "7D").strip().upper()
        return _ok(ctx.market.series(slug, range_key=range_key))

    @app.get("/api/v1/movers")
    @app.get("/api/movers")
    def movers():  # noqa: ANN202
        window = (request.args.get("window") or "1D").strip().upper()
        limit = _int_arg("limit", 5, low=1, high=25)
        return _ok(ctx.market.movers(window=window, limit=limit))

    @app.get("/api/v1/search")
    @app.get("/api/search")
    def search_assets():  # noqa: ANN202
        query = (request.args.get("q") or "").strip()
        if len(query) > 64:
            raise ValidationError("عبارت جستجو بیش از حد بلند است", "q")
        return _ok({"query": query, "items": ctx.market.search(query)})

    @app.get("/api/v1/sources")
    @app.get("/api/sources")
    def sources():  # noqa: ANN202
        """وضعیت منابع: آخرین اجرا، نرخ موفقیت و مدارشکن."""
        return _ok({
            "items": ctx.collector.provider_health(),
            "latest": [status.to_dict() for status in ctx.storage.sources.latest()],
            "database": ctx.storage.stats(),
        })

    @app.get("/api/v1/status")
    @app.get("/api/status")
    def status():  # noqa: ANN202
        """وضعیت سرویس، زمان‌بند و پایگاه داده."""
        return _ok({
            "scheduler": ctx.scheduler.status(),
            "database": ctx.storage.stats(),
            "history": ctx.storage.history.stats(),
            "sources": [status.to_dict() for status in ctx.storage.sources.latest()],
            "server_time": time.time(),
        })

    # -------------------------------------------------------------- watchlist
    @app.get("/api/v1/watchlist")
    @app.get("/api/watchlist")
    def watchlist_get():  # noqa: ANN202
        return _ok(ctx.market.watchlist(_owner(request)))

    @app.post("/api/v1/watchlist/<slug>")
    @app.post("/api/watchlist/<slug>")
    def watchlist_add(slug: str):  # noqa: ANN202
        """افزودن/برداشتن قلم — دکمهٔ ستاره در رابط."""
        if slug not in ASSETS:
            registry.get(slug)
        owner = _owner(request)
        added = ctx.storage.watchlist.toggle(owner, slug)
        return _ok({
            "slug": slug, "in_watchlist": added,
            "count": ctx.storage.watchlist.count(owner),
        })

    @app.delete("/api/v1/watchlist/<slug>")
    @app.delete("/api/watchlist/<slug>")
    def watchlist_delete(slug: str):  # noqa: ANN202
        owner = _owner(request)
        removed = ctx.storage.watchlist.remove(owner, slug)
        return _ok({
            "slug": slug, "removed": removed,
            "count": ctx.storage.watchlist.count(owner),
        })

    # ------------------------------------------------------------------ alerts
    @app.get("/api/v1/alerts")
    @app.get("/api/alerts")
    def alerts_list():  # noqa: ANN202
        page = _int_arg("page", 1, low=1, high=1000)
        page_size = _int_arg("page_size", 25, low=1, high=ctx.config.api.max_page_size)
        slug = (request.args.get("slug") or "").strip() or None
        if slug and slug not in ASSETS:
            registry.get(slug)
        view = ctx.engine.rules_view(
            slug=slug, limit=page_size, offset=(page - 1) * page_size,
        )
        view["pagination"] = {"page": page, "page_size": page_size}
        return _ok(view)

    @app.post("/api/v1/alerts")
    @app.post("/api/alerts")
    def alerts_create():  # noqa: ANN202
        """ساخت قاعدهٔ هشدار."""
        payload = _json_body()
        slug = _require_slug(payload)
        kind = _require_kind(payload)
        threshold = _require_number(payload, "threshold")
        one_shot = bool(payload.get("one_shot") or False)
        cooldown = _require_number(payload, "cooldown_seconds", required=False)
        note = str(payload.get("note") or "")[:200]
        rule = ctx.engine.create(
            slug, kind, float(threshold), owner=_owner(request), one_shot=one_shot,
            cooldown_seconds=int(cooldown) if cooldown is not None else None, note=note,
        )
        return _ok(
            {"rule": rule.to_dict(), "title": ASSETS[slug].title},
            status=201,
        )

    @app.patch("/api/v1/alerts/<int:rule_id>")
    @app.patch("/api/alerts/<int:rule_id>")
    def alerts_update(rule_id: int):  # noqa: ANN202
        """فعال/متوقف کردن قاعده."""
        payload = _json_body()
        raw = str(payload.get("status") or "").strip().lower()
        try:
            status_value = AlertStatus(raw)
        except ValueError as error:
            raise ValidationError("وضعیت باید active یا paused باشد", "status") from error
        rule = ctx.storage.alerts.set_status(rule_id, status_value)
        return _ok({"rule": rule.to_dict()})

    @app.delete("/api/v1/alerts/<int:rule_id>")
    @app.delete("/api/alerts/<int:rule_id>")
    def alerts_delete(rule_id: int):  # noqa: ANN202
        if not ctx.storage.alerts.delete(rule_id):
            from .core.errors import RuleNotFound

            raise RuleNotFound(rule_id)
        return _ok({"id": rule_id, "deleted": True})

    @app.post("/api/v1/alerts/preview")
    @app.post("/api/alerts/preview")
    def alerts_preview():  # noqa: ANN202
        """پیش‌نمایش بدون ساخت قاعده — «الان فعال می‌شد؟»"""
        payload = _json_body()
        slug = _require_slug(payload)
        kind = _require_kind(payload)
        threshold = _require_number(payload, "threshold")
        return _ok(ctx.engine.preview(kind, slug, float(threshold)))

    @app.get("/api/v1/events")
    @app.get("/api/events")
    def events_list():  # noqa: ANN202
        """دفتر رخدادهای هشدار."""
        page = _int_arg("page", 1, low=1, high=1000)
        page_size = _int_arg("page_size", 25, low=1, high=ctx.config.api.max_page_size)
        slug = (request.args.get("slug") or "").strip() or None
        include_suppressed = (request.args.get("suppressed", "1") or "1") not in {"0", "false"}
        view = ctx.engine.events_view(
            slug=slug, include_suppressed=include_suppressed,
            limit=page_size, offset=(page - 1) * page_size,
        )
        view["pagination"] = {"page": page, "page_size": page_size}
        return _ok(view)

    # ------------------------------------------------------------------ actions
    @app.post("/api/v1/collect")
    @app.post("/api/collect")
    def trigger_collect():  # noqa: ANN202
        """جمع‌آوری دستی — برای تأیید زندهٔ داده در دمو."""
        admin_required()
        result = ctx.market.refresh()
        ctx.scheduler.evaluate_alerts()
        seed_registry(ctx.storage)
        return _ok(result.to_dict(), status=200 if result.quotes_received else 503)

    @app.post("/api/v1/alerts/evaluate")
    @app.post("/api/alerts/evaluate")
    def trigger_evaluate():  # noqa: ANN202
        """ارزیابی دستی هشدارها بدون واکشی تازه."""
        admin_required()
        return _ok(ctx.scheduler.evaluate_alerts())

    # ---------------------------------------------------------------- bootstrap
    seed_registry(ctx.storage)
    return app


def _default_app() -> Flask:
    """ساخت نمونهٔ پیش‌فرض برای ابزارهای WSGI (مانند gunicorn).

    راه‌اندازی کامل (روشن‌کردن زمان‌بند) عمداً همین‌جا انجام می‌شود، نه در
    ``create_app``: مسیر WSGI نقطهٔ شروع پروسه است، پس زمان‌بند باید اینجا
    بالا بیاید؛ وگرنه روی سرور تولیدی هیچ جمع‌آوری خودکاری اجرا نمی‌شود و
    داشبورد برای همیشه دادهٔ کهنه نشان می‌دهد. ``create_app`` بدون عارضهٔ
    جانبی می‌ماند تا آزمون‌ها بدون زمان‌بند اجرا شوند.
    """
    context = AppContext.build()
    context.bootstrap()
    return create_app(context)


def __getattr__(name: str):
    """ساخت تنبل ``app`` — import کردن ماژول هیچ عارضهٔ جانبی ندارد."""
    if name == "app":
        return _default_app()
    raise AttributeError(name)


__all__ = ["DOCS", "OWNER_COOKIE", "create_app"]
