# -*- coding: utf-8 -*-
"""متن‌ها و قالب‌بندی پیام‌های ربات.

هر کارت قیمت پنج چیز را نشان می‌دهد: قیمت فعلی، تغییر، درصد تغییر، زمان
داده و منبع. تغییر تنها وقتی چاپ می‌شود که مبنای واقعی داشته باشد؛
در غیر این صورت «—» می‌آید.
"""
from __future__ import annotations

import time

from ..core import assets as asset_registry
from ..core.formatting import (
    arrow,
    fa_clock,
    fa_duration,
    fa_num,
    fa_pct,
    fa_plain,
    fa_price,
    fa_signed,
)
from ..core.models import AssetKind, Freshness, Quote
from ..storage import Alert, AlertDirection, AlertStatus

BRAND = "قیمت‌یار"
TAGLINE = "پایش هوشمند بازار طلا، ارز و رمزارز"

_SOURCE_LABELS = {
    "tgju": "tgju.org",
    "tgju-html": "tgju.org (صفحهٔ وب)",
    "coingecko": "CoinGecko",
}

_FRESHNESS_MARK = {
    Freshness.LIVE: "🟢 زنده",
    Freshness.STALE: "🟡 کهنه",
    Freshness.UNAVAILABLE: "🔴 دردسترس نیست",
}


def source_label(source: str) -> str:
    """نام خوانا برای منبع داده."""
    return _SOURCE_LABELS.get(source, source or "ناشناخته")


def title_of(slug: str) -> str:
    asset = asset_registry.ASSETS.get(slug)
    return asset.title if asset else slug


def emoji_of(slug: str) -> str:
    asset = asset_registry.ASSETS.get(slug)
    return asset.emoji if asset else "💠"


# --------------------------------------------------------------------- cards
def render_change(quote: Quote) -> str:
    """خط تغییر — با مبنای صریح یا «—» صادقانه."""
    if quote.change_pct is None or quote.change_abs is None:
        return "تغییر: — <i>(تاریخچهٔ کافی برای محاسبه نیست)</i>"
    direction = quote.direction
    decimals = quote.decimals
    basis = f" <i>{quote.change_basis}</i>" if quote.change_basis else ""
    return (
        f"تغییر: {arrow(direction)} {fa_signed(quote.change_abs, decimals)} "
        f"({fa_pct(quote.change_pct)}){basis}"
    )


def render_price_card(quote: Quote, *, heading: bool = True) -> str:
    """کارت کامل یک قلم."""
    asset = asset_registry.ASSETS.get(quote.slug)
    lines: list[str] = []
    if heading:
        lines.append(f"{emoji_of(quote.slug)} <b>{title_of(quote.slug)}</b>")
    lines.append(f"قیمت: <b>{fa_price(quote.price, quote.unit, quote.decimals)}</b>")
    lines.append(render_change(quote))
    if quote.day_low and quote.day_high and quote.day_high > quote.day_low:
        lines.append(
            f"بازهٔ روز: {fa_price(quote.day_low, quote.unit, quote.decimals)}"
            f" تا {fa_price(quote.day_high, quote.unit, quote.decimals)}"
        )
    lines.append(
        f"آخرین داده: {fa_duration(quote.source_age_seconds)} — منبع: {source_label(quote.source)}"
    )
    lines.append(f"وضعیت: {_FRESHNESS_MARK[quote.freshness]}")
    if quote.freshness is Freshness.STALE:
        lines.append(
            "⚠️ این عدد از آخرین دادهٔ معتبر است، نه قیمت لحظه‌ای."
        )
    if asset is not None and asset.unit == "usd":
        lines.append("<i>قیمت رمزارزها به دلار آمریکا است.</i>")
    return "\n".join(lines)


def render_compact(quote: Quote) -> str:
    """یک خط خلاصه برای فهرست‌ها."""
    price = fa_price(quote.price, quote.unit, quote.decimals)
    if quote.change_pct is None:
        return f"{emoji_of(quote.slug)} <b>{title_of(quote.slug)}</b>: {price}"
    return (
        f"{emoji_of(quote.slug)} <b>{title_of(quote.slug)}</b>: {price} "
        f"{arrow(quote.direction)} {fa_pct(quote.change_pct)}"
    )


def render_market(
    quotes: dict[str, Quote],
    *,
    title: str,
    missing: list[str] | None = None,
    from_cache: bool = False,
) -> str:
    """فهرست چند قلم با هشدارهای لازم."""
    lines = [f"📊 <b>{title}</b>", ""]
    if not quotes:
        lines.append("هیچ داده‌ای در دسترس نیست.")
    else:
        for slug in _order_slugs(quotes):
            lines.append(render_compact(quotes[slug]))
    if missing:
        names = "، ".join(title_of(s) for s in missing)
        lines.append("")
        lines.append(f"⛔ بدون داده: {names}")
    if from_cache:
        lines.append("")
        lines.append("<i>از کش کوتاه‌مدت پاسخ داده شد.</i>")
    lines.append("")
    lines.append("<i>هیچ توصیهٔ سرمایه‌گذاری ارائه نمی‌شود؛ این داده صرفاً اطلاعاتی است.</i>")
    return "\n".join(lines)


def _order_slugs(quotes: dict[str, Quote]) -> list[str]:
    """ترتیب نمایش: طلا، سکه، ارز، رمزارز."""
    ordered: list[str] = []
    for kind in (AssetKind.GOLD, AssetKind.COIN, AssetKind.CURRENCY, AssetKind.CRYPTO):
        for slug in quotes:
            if slug in ordered:
                continue
            asset = asset_registry.ASSETS.get(slug)
            if asset is not None and asset.kind is kind:
                ordered.append(slug)
    for slug in quotes:
        if slug not in ordered:
            ordered.append(slug)
    return ordered


# --------------------------------------------------------------------- alerts
def render_alert_created(alert: Alert) -> str:
    return (
        "✅ هشدار ثبت شد\n\n"
        f"{emoji_of(alert.slug)} <b>{title_of(alert.slug)}</b>\n"
        f"شرط: قیمت <b>{alert.direction.label} {fa_num(alert.target)}</b> "
        f"{'دلار' if _is_usd(alert.slug) else 'تومان'}\n"
        f"شناسه: #{alert.id}\n"
        + (
            "پس از فعال‌شدن یک‌بار خبر می‌دهم و هشدار خاموش می‌شود."
            if alert.one_shot
            else "پس از فعال‌شدن خبر می‌دهم و پایش ادامه دارد."
        )
    )


def render_alert_triggered(alert: Alert, quote: Quote) -> str:
    """متن اعلان — صریح دربارهٔ قیمت، زمان و منبع."""
    return (
        "🔔 <b>هشدار قیمت فعال شد</b>\n\n"
        f"{emoji_of(alert.slug)} <b>{title_of(alert.slug)}</b>\n"
        f"قیمت فعلی: <b>{fa_price(quote.price, quote.unit, quote.decimals)}</b>\n"
        f"شرط شما: {alert.direction.label} {fa_num(alert.target)}\n"
        f"زمان داده: {fa_clock(quote.observed_at)} — منبع: {source_label(quote.source)}\n"
        f"شناسهٔ هشدار: #{alert.id}"
    )


def render_alerts(rows: list[Alert], *, limit: int) -> str:
    """فهرست هشدارهای کاربر."""
    if not rows:
        return (
            "🔔 هنوز هشداری نساخته‌اید.\n\n"
            "برای ساخت: مثلاً بنویسید «دلار بالای ۲۵۰۰۰۰» یا از دکمه‌ها استفاده کنید."
        )
    lines = [f"🔔 <b>هشدارهای شما</b> ({fa_plain(len(rows))} از {fa_plain(limit)})", ""]
    for alert in rows:
        unit = "دلار" if _is_usd(alert.slug) else "تومان"
        mark = {
            AlertStatus.ACTIVE: "🟢",
            AlertStatus.PAUSED: "⏸",
            AlertStatus.TRIGGERED: "✅",
            AlertStatus.DISABLED: "🚫",
        }[alert.status]
        lines.append(
            f"{mark} #{alert.id} {emoji_of(alert.slug)} {title_of(alert.slug)} — "
            f"{alert.direction.label} {fa_num(alert.target)} {unit}"
            f" <i>({alert.status.label})</i>"
        )
    lines.append("")
    lines.append("از دکمه‌ها برای خاموش/روشن یا حذف استفاده کنید.")
    return "\n".join(lines)


def render_alert_events(rows: list) -> str:
    """گزارش آخرین رخدادهای هشدار — شفافیت دربارهٔ سرکوب و خطا."""
    kinds = {
        "created": "📝 ساخته شد",
        "updated": "✏️ ویرایش شد",
        "triggered": "🔔 اعلان رفت",
        "suppressed": "⏳ اعلان به تعویق افتاد",
        "error": "⚠️ خطای ارسال",
        "deleted": "🗑 حذف شد",
    }
    if not rows:
        return "📜 رویدادی ثبت نشده است."
    lines = ["📜 <b>آخرین رویدادهای هشدار</b>", ""]
    for row in rows:
        label = kinds.get(str(row["kind"]), str(row["kind"]))
        when = fa_duration(max(0.0, time.time() - float(row["created_at"])))
        detail = f" — <i>{row['detail']}</i>" if row["detail"] else ""
        lines.append(f"{label} · {title_of(str(row['slug']))} · {when}{detail}")
    return "\n".join(lines)


def _is_usd(slug: str) -> bool:
    asset = asset_registry.ASSETS.get(slug)
    return bool(asset and asset.unit == "usd")


# --------------------------------------------------------------------- static
def render_welcome(name: str | None = None) -> str:
    who = f"{name} عزیز، " if name else ""
    return (
        f"سلام {who}👋\n"
        f"من <b>{BRAND}</b> هستم؛ {TAGLINE}.\n\n"
        "قیمت‌ها لحظه‌ای و از منبع واقعی خوانده می‌شوند و هیچ قیمتی در ربات "
        "ذخیره یا بازتولید نمی‌شود.\n\n"
        "<b>دستورهای اصلی</b>\n"
        "• /market — نمای بازار\n"
        "• /price دلار — قیمت یک قلم\n"
        "• /gold یا /crypto — نگاه دسته‌ای\n"
        "• /chart بیت‌کوین — نمودار تاریخچه\n"
        "• /alert — ساخت هشدار قیمت\n"
        "• /watchlist — دیده‌بان شخصی\n"
        "• /status — وضعیت منابع داده\n"
        "• /help — راهنمای کامل\n\n"
        "<i>این ربات توصیهٔ سرمایه‌گذاری نمی‌دهد.</i>"
    )


HELP = (
    f"📖 <b>راهنمای {BRAND}</b>\n\n"
    "<b>قیمت‌ها</b>\n"
    "/market — خلاصهٔ بازار\n"
    "/price [نام] — قیمت یک قلم (مثال: /price سکه امامی)\n"
    "/gold — طلا و سکه\n"
    "/crypto — رمزارزها\n"
    "/currency — ارزها\n"
    "/chart [نام] — نمودار تاریخچهٔ قیمت\n\n"
    "<b>هشدارها</b>\n"
    "/alert — ساخت هشدار\n"
    "/alerts — مدیریت هشدارها\n"
    "/events — آخرین رویدادهای هشدار (چرا اعلان نرفت؟)\n\n"
    "<b>شخصی</b>\n"
    "/watchlist — دیده‌بان\n"
    "/status — سلامت منابع داده و کش\n"
    "/about — دربارهٔ داده‌ها و محدودیت‌ها\n\n"
    "می‌توانید نام قلم را مستقیم بنویسید؛ همان پاسخ قیمت را می‌گیرید."
)

ABOUT = (
    "ℹ️ <b>دربارهٔ داده‌ها</b>\n\n"
    "<b>منابع</b>\n"
    "• بازار داخل (طلا، سکه، ارز): tgju.org\n"
    "• رمزارزها: CoinGecko و در صورت خطا tgju\n\n"
    "<b>رفتار واقعی داده</b>\n"
    "• هر درخواست از منبع زنده یا کش کوتاه‌مدت معتبر پاسخ می‌گیرد.\n"
    "• اگر منبع در دسترس نباشد، همان لحظه تلاش مجدد و سپس fallback انجام "
    "می‌شود و در نهایت صادقانه «دردسترس نیست» نشان داده می‌شود.\n"
    "• هیچ قیمت ساختگی یا پیش‌فرضی نمایش داده نمی‌شود.\n"
    "• اگر داده از حدی قدیمی‌تر باشد، با برچسب «کهنه» و هشدار نمایش داده "
    "می‌شود، نه به‌عنوان قیمت لحظه‌ای.\n\n"
    "<b>محدودیت‌ها</b>\n"
    "• درصد تغییر طلا/سکه/ارز از تاریخچهٔ خود ربات محاسبه می‌شود؛ خوراک tgju "
    "برای این اقلام تغییر روزانه منتشر نمی‌کند.\n"
    "• سکهٔ گرمی فقط از صفحهٔ وب tgju خوانده می‌شود و ممکن است نباشد.\n"
    "• سقف نرخ درخواست منابع عمومی رعایت می‌شود؛ بنابراین کش ۶۰ ثانیه‌ای است.\n"
)


def render_unavailable(names: list[str], detail: str = "") -> str:
    """پیام نبود داده — بدون هیچ عددی."""
    label = "، ".join(names) if names else "قیمت‌ها"
    lines = [
        "⛔ <b>دادهٔ قابل‌اتکا در دسترس نیست</b>",
        "",
        f"برای {label} نتوانستم از منبع واقعی قیمت بگیرم. "
        "به‌جای نمایش عددی که مطمئن نیستم، چیزی نشان نمی‌دهم.",
        "",
        "چند لحظه بعد دوباره تلاش کنید. اگر ادامه داشت، /status وضعیت منابع را نشان می‌دهد.",
    ]
    if detail:
        lines.append(f"\n<i>جزئیات فنی: {detail[:200]}</i>")
    return "\n".join(lines)


def render_status(statuses, cache_items: int, cache_age: float, history_stats: dict) -> str:
    """وضعیت منابع، کش و تاریخچه."""
    lines = ["🩺 <b>وضعیت سرویس</b>", ""]
    if not statuses:
        lines.append("هنوز درخواستی به منابع نرفته است.")
    for status in statuses:
        mark = "🟢" if status.ok else "🔴"
        info = f"{fa_plain(status.items)} قلم" if status.ok else status.error[:80]
        lines.append(f"{mark} {source_label(status.name)} — {fa_plain(status.latency_ms)}ms — {info}")
    lines.append("")
    lines.append(
        f"کش: {fa_plain(cache_items)} قلم"
        + (f" — سن {fa_duration(cache_age)}" if cache_items else "")
    )
    lines.append(
        f"تاریخچه: {fa_plain(history_stats.get('points', 0))} نقطه "
        f"برای {fa_plain(history_stats.get('assets', 0))} قلم"
    )
    return "\n".join(lines)


def render_chart_caption(slug: str, points: int, window_hours: int) -> str:
    return (
        f"📈 <b>نمودار {title_of(slug)}</b>\n"
        f"{fa_plain(points)} نقطهٔ ثبت‌شده در {fa_plain(window_hours)} ساعت گذشته.\n"
        "<i>نمودار از تاریخچهٔ واقعی ربات ساخته شده است.</i>"
    )


def search_not_found(query: str) -> str:
    names = "، ".join(a.title for a in asset_registry.all_assets_ordered())
    return (
        f"قلمی با نام «{query}» پیدا نکردم.\n\n"
        f"اقلام موجود: {names}\n\n"
        "یا از دکمه‌های بازار استفاده کنید."
    )


def render_watchlist(slugs: list[str], quotes: dict[str, Quote], limit: int) -> str:
    if not slugs:
        return (
            "⭐ دیده‌بان خالی است.\n\n"
            "از فهرست قیمت‌ها یا با دستور /price، قلم مورد نظر را اضافه کنید."
        )
    lines = [f"⭐ <b>دیده‌بان شما</b> ({fa_plain(len(slugs))} از {fa_plain(limit)})", ""]
    for slug in slugs:
        quote = quotes.get(slug)
        if quote is None:
            lines.append(f"{emoji_of(slug)} <b>{title_of(slug)}</b>: ⛔ بدون داده")
        else:
            lines.append(render_compact(quote))
    return "\n".join(lines)


def render_error(detail: str = "") -> str:
    lines = ["⚠️ در پردازش درخواست خطایی رخ داد."]
    if detail:
        lines.append(f"<i>{detail[:200]}</i>")
    return "\n".join(lines)


__all__ = [
    "ABOUT",
    "BRAND",
    "HELP",
    "render_alert_created",
    "render_alert_events",
    "render_alert_triggered",
    "render_alerts",
    "render_chart_caption",
    "render_compact",
    "render_error",
    "render_market",
    "render_price_card",
    "render_status",
    "render_unavailable",
    "render_watchlist",
    "render_welcome",
    "search_not_found",
    "source_label",
    "title_of",
]
