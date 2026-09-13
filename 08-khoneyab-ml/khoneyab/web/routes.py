# -*- coding: utf-8 -*-
"""مسیرهای صفحه — هر تابع یک صفحهٔ کامل HTML برمی‌گرداند.

قاعده‌ها:

* **همه‌چیز از ``services`` می‌آید.** این لایه چیزی از دیتاست یا مدل
  نمی‌داند؛ فقط نتیجهٔ آماده را به قالب می‌دهد.
* **ورودی نامعتبر خطا نیست.** فیلتر خارج از دامنه نادیده گرفته می‌شود و
  صفحه همچنان می‌آید.
* **عملیات نوشتنی فقط POST.** افزودن به مقایسه و نشان‌کردن، وضعیت نشست را
  عوض می‌کنند و باید از تازه‌سازی تصادفی لینک‌ها در امان باشند.
"""
from __future__ import annotations

from flask import (Blueprint, abort, jsonify, redirect, render_template,
                   request, url_for)

from .. import services
from ..photos import license_family
from ..search import SORT_OPTIONS
from . import params, presenters, session as store
from .context import shell as _shell

bp = Blueprint("pages", __name__)


@bp.get("/")
def home():
    """صفحهٔ خانه — جست‌وجو در کانون، پیش از هر چیز دیگر."""
    overview = services.overview()
    insights = services.insights()
    featured = services.featured(3)
    cards = [
        presenters.card_view(item,
                             comparing=item.id in store.compare_ids(),
                             saved=item.id in store.saved_ids())
        for item in featured
    ]
    return render_template(
        "home.html",
        **_shell("home"),
        overview=overview,
        insights=insights,
        cards=cards,
        hero=presenters.hero_view(services.photos().cover(0)),
        district_chart=presenters.district_chart(8),
        distribution_chart=presenters.distribution_chart(),
        bounds=services.bounds(),
        districts=services.districts(),
        total_photos=services.photos().total,
    )


@bp.get("/search")
def search_page():
    """فهرست ملک‌ها با فیلتر، مرتب‌سازی و صفحه‌بندی."""
    query = params.search_query(request.args)
    result = services.search(query)
    compare_ids = store.compare_ids()
    saved_ids = store.saved_ids()
    cards = [
        presenters.card_view(item, comparing=item.id in compare_ids,
                             saved=item.id in saved_ids)
        for item in result.items
    ]
    return render_template(
        "search.html",
        **_shell("search"),
        cards=cards,
        result=result,
        query=query,
        sort_options=SORT_OPTIONS,
        bounds=services.bounds(),
        districts=services.districts(),
        active_filters=query.active_filters(),
        median_price=result.median_price(),
        median_price_m2=result.median_price_per_m2(),
        query_string=_query_string(request.args, drop=("page",)),
    )


@bp.get("/listing")
def listing_by_query():
    """پشتیبانی از نشانی قدیمی ``/listing?item=KH-1001``."""
    identifier = request.args.get("item", "")
    if not identifier:
        abort(404)
    return redirect(url_for("pages.listing_page", listing_id=identifier), code=301)


@bp.get("/listing/<listing_id>")
def listing_page(listing_id: str):
    """صفحهٔ یک ملک — عکس، مشخصات، برآورد مدل و دلیلش."""
    item = services.listing(listing_id)
    if item is None:
        abort(404)

    explanation = services.explanation_for_listing(item)
    summary = services.summary_for(explanation)
    gap = ((item.price - explanation.price) / explanation.price
           if explanation.price else 0.0)

    comparables = [
        presenters.card_view(other) for other in explanation.comparables.items[:3]
    ]
    return render_template(
        "detail.html",
        **_shell("search"),
        item=item,
        card=presenters.card_view(item, comparing=item.id in store.compare_ids(),
                                  saved=item.id in store.saved_ids()),
        gallery=presenters.gallery_view(item),
        specs=presenters.specs_view(item),
        estimate=presenters.estimate_view(explanation, summary),
        gap=gap,
        comparables=comparables,
        credit=presenters.credit_note(item),
    )


@bp.get("/compare")
def compare_page():
    """چند ملک کنار هم — جدول، نمودار و نشانی اشتراکی."""
    shared = params.ids(request.args.get("ids"))
    if shared:
        valid = [identifier for identifier in shared
                 if services.listing(identifier) is not None]
        if valid:
            store.set_compare(valid)

    items = services.resolve(store.compare_ids())
    if not items:
        return render_template("compare.html", **_shell("compare"),
                               items=[], cards=[], table=None, charts=None,
                               share_url=None)

    explanations = {item.id: services.explanation_for_listing(item) for item in items}
    prices = [explanations[item.id].price for item in items]
    rows = _compare_rows(items, explanations)
    meters, grouped = presenters.compare_chart(items, prices)
    identifiers = ",".join(item.id for item in items)
    share_url = f"/compare?ids={identifiers}"
    return render_template(
        "compare.html",
        **_shell("compare"),
        items=items,
        cards=[presenters.card_view(item) for item in items],
        headers=[item.id for item in items],
        table=rows,
        charts={"meters": meters, "grouped": grouped},
        share_url=share_url,
        cheapest=min(items, key=lambda entry: entry.price_per_m2),
        dearest=max(items, key=lambda entry: entry.price_per_m2),
        max_compare=store.MAX_COMPARE,
    )


def _compare_rows(items, explanations) -> list[tuple[str, list[str]]]:
    """ردیف‌های جدول مقایسه — برچسب و یک مقدار برای هر ملک."""
    from ..labels import fa_number, fa_percent

    rows = [
        ("عنوان", [item.title for item in items]),
        ("منطقه", [item.district_label for item in items]),
        ("قیمت آگهی", [fa_number(item.price) for item in items]),
        ("ارزش برآوردی", [fa_number(explanations[item.id].price) for item in items]),
        ("اختلاف با برآورد", [
            fa_percent((item.price - explanations[item.id].price) / explanations[item.id].price,
                       signed=True)
            if explanations[item.id].price else "—"
            for item in items
        ]),
        ("قیمت هر متر", [fa_number(item.price_per_m2) for item in items]),
        ("متراژ", [f"{fa_number(item.area)} متر" for item in items]),
        ("اتاق خواب", [item.bedrooms_label for item in items]),
        ("سن بنا", [f"{fa_number(item.age)} سال" for item in items]),
        ("طبقه", [item.floor_label for item in items]),
        ("نوع ملک", [item.property_type for item in items]),
        ("پارکینگ", ["دارد" if item.parking else "ندارد" for item in items]),
        ("انباری", ["دارد" if item.storage else "ندارد" for item in items]),
        ("آسانسور", ["دارد" if item.elevator else "ندارد" for item in items]),
    ]
    return rows


@bp.get("/estimate")
def estimate_page():
    """برآورد قیمت — فرم در کنار، نتیجه و دلیلش در برابر."""
    stored = store.stored_estimate()
    features = params.estimate_features(request.args, fallback=stored)
    explanation = services.explanation_for_features(features)
    summary = services.summary_for(explanation)
    comparables = [presenters.card_view(item)
                   for item in explanation.comparables.items[:3]]
    return render_template(
        "estimate.html",
        **_shell("estimate"),
        features=features,
        estimate=presenters.estimate_view(explanation, summary),
        comparables=comparables,
        defaults=params.default_features(),
        districts=services.districts(),
        presets=PRESETS,
        api_url=url_for("api.estimate"),
    )


#: نمونه‌های آمادهٔ فرم برآورد — برای دیدن تفاوت منطقه و متراژ در یک نگاه.
PRESETS: dict[str, dict] = {
    "آپارتمان میان‌شهر": {"district": 8, "area": 85, "bedrooms": 2, "age": 12,
                          "floor": 2, "parking": 1, "storage": 1, "elevator": 1},
    "واحد نوساز شمال شهر": {"district": 1, "area": 165, "bedrooms": 3, "age": 1,
                            "floor": 6, "parking": 1, "storage": 1, "elevator": 1},
    "خانهٔ ویلایی حاشیه": {"district": 22, "area": 240, "bedrooms": 4, "age": 8,
                           "floor": 0, "parking": 1, "storage": 1, "elevator": 0},
}


@bp.get("/analytics")
def analytics_page():
    """تحلیل بازار — تجمیع‌های واقعی کاتالوگ و معیارهای مدل."""
    expensive, affordable = presenters.movers_charts(6)
    frame = services.districts()
    table = [
        {
            "district": row["district_name"],
            "listings": row["listings"],
            "median_price": row["median_price"],
            "median_price_m2": row["median_price_m2"],
            "median_age": row["mean_age"],
            "luxury_share": row["luxury_share"],
        }
        for _, row in frame.iterrows()
    ]
    return render_template(
        "analytics.html",
        **_shell("analytics"),
        overview=services.overview(),
        insights=services.insights(),
        table=table,
        expensive_chart=expensive,
        affordable_chart=affordable,
        distribution_chart=presenters.distribution_chart(),
        per_m2_chart=presenters.per_m2_chart(),
        area_chart=presenters.area_chart(),
        bedrooms_chart=presenters.bedrooms_chart(),
        importance_chart=presenters.importance_chart(),
        interval_chart=presenters.interval_chart(),
    )


@bp.get("/methodology")
def methodology_page():
    """متدولوژی — دیتاست، مدل، معیارها، محدودیت‌ها و اعتبار عکس‌ها."""
    library = services.photos()
    credits = sorted(
        (_credit_view(entry) for entry in library.entries),
        key=lambda entry: (entry["kind"], entry["file"]),
    )
    return render_template(
        "methodology.html",
        **_shell("methodology"),
        insights=services.insights(),
        metrics=services.metrics(),
        credits=credits,
        importance_chart=presenters.importance_chart(),
        interval_chart=presenters.interval_chart(),
    )


@bp.get("/robots.txt")
def robots():
    """خزنده‌ها را راه می‌دهیم؛ این یک سایت نمایشی عمومی است."""
    body = "User-agent: *\nAllow: /\n"
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


def _credit_view(entry: dict) -> dict:
    """یک ردیف اعتبار عکس — با بندانگشتی، نه نام خام فایل.

    میز عکس‌ها با نام فایل خام پر می‌شد؛ فهرستی بلند از رشته‌های لاتین که
    هیچ کمکی به خواننده نمی‌کرد. اینجا جای نام فایل، خود عکس دیده می‌شود.
    """
    return {
        "file": entry.get("file", ""),
        "kind": "نمای بیرونی" if entry.get("kind") == "exterior" else "نمای داخلی",
        "author": entry.get("author") or "—",
        "license": license_family(entry.get("license")),
        "provider": entry.get("provider") or "—",
        "page": entry.get("page", ""),
        "thumb": presenters.card_thumb(entry.get("file")),
    }


def _query_string(args, *, drop: tuple[str, ...] = ()) -> str:
    """رشتهٔ پرس‌وجوی فعلی بدون کلیدهای مشخص — برای لینک صفحه‌بندی."""
    pairs = [(key, value) for key, value in args.items(multi=True)
             if key not in drop]
    if not pairs:
        return ""
    from urllib.parse import urlencode

    return "&" + urlencode(pairs)


# ------------------------------------------------------------------ عملیات نشست
def _wants_json() -> bool:
    if request.headers.get("X-Requested-With") == "fetch":
        return True
    return "application/json" in request.headers.get("Accept", "")


def _back(default: str) -> str:
    target = request.form.get("next") or request.referrer or default
    # فقط مسیرهای داخلی — جلوی بازگردانی به دامنهٔ بیرونی گرفته می‌شود.
    if not target.startswith("/") or target.startswith("//"):
        return default
    return target


@bp.post("/compare/toggle/<listing_id>")
def toggle_compare(listing_id: str):
    item = services.listing(listing_id)
    if item is None:
        abort(404)
    was_in = listing_id in store.compare_ids()
    added = store.toggle_compare(listing_id)
    payload = {"id": listing_id, "in_compare": added,
               "count": len(store.compare_ids()), "full": store.compare_full(),
               "reason": "" if added or was_in else "full"}
    if _wants_json():
        return jsonify(payload)
    return redirect(_back("/compare"))


@bp.post("/compare/clear")
def clear_compare():
    store.clear_compare()
    if _wants_json():
        return jsonify({"in_compare": False, "count": 0, "full": False, "reason": ""})
    return redirect(_back("/compare"))


@bp.post("/saved/toggle/<listing_id>")
def toggle_saved(listing_id: str):
    item = services.listing(listing_id)
    if item is None:
        abort(404)
    saved = store.toggle_saved(listing_id)
    payload = {"id": listing_id, "saved": saved, "count": len(store.saved_ids())}
    if _wants_json():
        return jsonify(payload)
    return redirect(_back("/search"))


@bp.post("/estimate/save")
def save_estimate():
    """ذخیرهٔ مشخصات فعلی فرم برآورد در نشست — تا بازگشت به صفحه پاک نشود."""
    features = params.estimate_features(request.form, fallback=store.stored_estimate())
    store.set_estimate(features)
    if _wants_json():
        return jsonify({"saved": True, "features": features})
    return redirect("/estimate")


@bp.get("/saved")
def saved_page():
    """فهرست نشان‌شده‌ها — همان شبکهٔ کارت، بدون فیلتر."""
    items = services.resolve(store.saved_ids())
    cards = [presenters.card_view(item, saved=True, comparing=item.id in store.compare_ids())
             for item in items]
    return render_template("saved.html", **_shell("saved"), cards=cards)
