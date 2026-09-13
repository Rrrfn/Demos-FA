# -*- coding: utf-8 -*-
"""API عمومی — همان داده‌ای که صفحه‌ها نشان می‌دهند، به شکل JSON.

سه قاعده در همهٔ پاسخ‌ها رعایت می‌شود:

۱) **پاسخ یک‌شکل.** یا ``{"ok": true, "data": …}`` یا
   ``{"ok": false, "error": {"code": …, "message": …}}``. مصرف‌کننده لازم
   نیست دو حالت را حدس بزند.

۲) **ورودی نامعتبر، خطای روشن.** مقدار خارج از دامنه با کد ۴۰۰ و نام همان
   پارامتر برمی‌گردد؛ سکوت کردن و برگرداندن عدد پیش‌فرض، خطا را پنهان می‌کند.

۳) **هیچ عدد جعلی.** اگر مدل یا داده در دسترس نباشد، پاسخ
   ``available: false`` می‌گیرد، نه یک قیمت ساختگی.
"""
from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from .. import services
from ..config import AGE_RANGE, AREA_RANGE, BEDROOM_RANGE, DISTRICT_CODES, FLOOR_RANGE
from ..search import SORT_OPTIONS
from . import STARTED_AT, params, presenters, session as store

bp = Blueprint("api", __name__, url_prefix="/api")


def ok(data: dict, status: int = 200):
    return jsonify({"ok": True, "data": data}), status


def fail(code: str, message: str, status: int = 400, **extra):
    error = {"code": code, "message": message}
    error.update(extra)
    return jsonify({"ok": False, "error": error}), status


def fail_field(error: dict, status: int = 400):
    """پاسخ خطا برای یک پارامتر نامعتبر — با نام همان پارامتر."""
    return fail("invalid_parameter", error.get("message", "ورودی نامعتبر است."),
                status, field=error.get("field", ""))


def _field(raw: object, name: str, low: int, high: int) -> tuple[int | None, dict | None]:
    """خواندن یک عدد با بازهٔ مجاز. خروجی: (مقدار، خطا)."""
    if raw is None:
        return None, None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None, {"field": name, "message": f"مقدار «{name}» باید عدد باشد."}
    if value < low or value > high:
        return None, {"field": name,
                      "message": f"«{name}» باید بین {low} و {high} باشد."}
    return value, None


@bp.get("/health")
def health():
    """وضعیت سرویس — برای پایش استقرار و بررسی سلامت پس از دپلوی."""
    return ok({
        "status": "ok",
        "uptime_seconds": round(time.time() - STARTED_AT, 1),
        "listings": services.overview()["listings"],
        "photos": services.photos().total,
        "model": services.metrics().get("best_model", ""),
        "data_note": "داده سینتتیک — قیمت واقعی بازار نیست.",
    })


@bp.get("/overview")
def overview():
    """شاخص‌های سرصفحه‌ای بازار."""
    return ok({"overview": services.overview(), "model": services.insights()})


@bp.get("/listings")
def listings():
    """جست‌وجوی صفحه‌بندی‌شده روی کاتالوگ."""
    query = params.search_query(request.args)
    result = services.search(query)
    cards = [presenters.card_view(item) for item in result.items]
    return ok({
        "total": result.total,
        "page": result.page,
        "pages": result.pages,
        "page_size": result.page_size,
        "has_next": result.has_next,
        "has_prev": result.has_prev,
        "median_price": result.median_price(),
        "median_price_m2": result.median_price_per_m2(),
        "sort": query.sort,
        "sort_options": list(SORT_OPTIONS),
        "filters": list(query.active_filters()),
        "items": cards,
    })


@bp.get("/listings/<listing_id>")
def listing_detail(listing_id: str):
    """یک ملک، همراه با برآورد مدل و دلیلش."""
    item = services.listing(listing_id)
    if item is None:
        return fail("not_found", f"ملکی با شناسهٔ {listing_id} وجود ندارد.", 404)
    explanation = services.explanation_for_listing(item)
    return ok({
        "listing": presenters.card_view(item),
        "specs": dict(presenters.specs_view(item)),
        "estimate": presenters.estimate_view(
            explanation, services.summary_for(explanation)),
        "comparables": [presenters.card_view(other)
                        for other in explanation.comparables.items],
    })


@bp.get("/estimate")
def estimate():
    """برآورد ارزش ملک از مشخصات ورودی.

    پارامترها: ``district`` ``area`` ``bedrooms`` ``age`` ``floor`` و
    ``parking`` ``storage`` ``elevator`` (۰ یا ۱). هر پارامتر نامعتبر با کد
    ۴۰۰ رد می‌شود. در نبود پارامتر، مقدار پیش‌فرض نشست یا شهر می‌نشیند.
    """
    features = dict(params.default_features())
    stored = store.stored_estimate()
    if stored:
        features.update(stored)

    bounds = {
        "district": (min(DISTRICT_CODES), max(DISTRICT_CODES)),
        "area": AREA_RANGE,
        "bedrooms": BEDROOM_RANGE,
        "age": AGE_RANGE,
        "floor": FLOOR_RANGE,
        "parking": (0, 1), "storage": (0, 1), "elevator": (0, 1),
    }
    for name, (low, high) in bounds.items():
        value, error = _field(request.args.get(name), name, low, high)
        if error:
            return fail_field(error)
        if value is not None:
            features[name] = value

    explanation = services.explanation_for_features(features)
    return ok({
        "features": features,
        "explanation": presenters.estimate_view(
            explanation, services.summary_for(explanation)),
        "available": True,
    })


@bp.get("/analytics")
def analytics():
    """تجمیع‌های بازار و معیارهای مدل."""
    return ok({
        "overview": services.overview(),
        "districts": services.districts()[
            ["district", "district_name", "listings", "median_price",
             "median_price_m2", "mean_area", "mean_age", "luxury_share"]
        ].to_dict("records"),
        "model": services.insights(),
    })


@bp.get("/methodology")
def methodology():
    """متدولوژی مدل و محدودیت‌هایی که باید همراه عددها خوانده شوند."""
    metrics = services.metrics()
    return ok({
        "best_model": metrics.get("best_model"),
        "n_samples": metrics.get("n_samples"),
        "cv_folds": metrics.get("cv_folds"),
        "test_size": metrics.get("test_size"),
        "results": metrics.get("results", {}),
        "importance": metrics.get("importance", []),
        "interval": metrics.get("interval", {}),
        "limitations": [
            "دادهٔ آموزش سینتتیک است و از معاملات واقعی بازار نمی‌آید.",
            "مدل رابطهٔ ویژگی‌ها با قیمت را از همان دادهٔ سینتتیک یاد گرفته است.",
            "بازهٔ اطمینان روی نیمهٔ آزمون کالیبره شده و پوشش آن اندازه‌گیری شده است.",
        ],
        "data_note": metrics.get("data_note", ""),
    })
