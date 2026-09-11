# -*- coding: utf-8 -*-
"""هندلرهای بازار: نمای کلی، قیمت یک قلم، دسته‌ها و نمودار."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ...core import assets as asset_registry
from ...core.errors import PriceUnavailable
from ...core.models import AssetKind
from ...services import ChartUnavailable, Services, render_price_chart_async
from .. import keyboards, texts

log = logging.getLogger("ghematyar.handlers.market")

_KIND_COMMANDS: dict[str, AssetKind] = {
    "gold": AssetKind.GOLD,
    "coins": AssetKind.COIN,
    "coin": AssetKind.COIN,
    "crypto": AssetKind.CRYPTO,
    "currency": AssetKind.CURRENCY,
}


async def _send_market(message: Message, services: Services, slugs: list[str], title: str) -> None:
    """نمای فهرستی با نمایش صادقانهٔ اقلام بی‌داده."""
    try:
        snapshot = await services.market.snapshot(slugs)
    except PriceUnavailable as exc:
        await message.answer(texts.render_unavailable(exc.slugs, exc.detail))
        return
    missing = [s for s in slugs if s not in snapshot.quotes]
    await message.answer(
        texts.render_market(
            snapshot.quotes, title=title, missing=missing, from_cache=snapshot.from_cache
        ),
        reply_markup=keyboards.market_keyboard(),
    )


async def cmd_market(message: Message, services: Services) -> None:
    """نمای کلی بازار — اقلام شاخص هر دسته."""
    slugs = list(asset_registry.FEATURED)
    # چند قلم دیگر هم اضافه می‌کنیم تا تصویر کامل‌تر شود
    for extra in ("geram24", "mesghal", "sekeb", "aed", "tether", "solana"):
        if extra not in slugs and asset_registry.exists(extra):
            slugs.append(extra)
    await _send_market(message, services, slugs, "نمای بازار")


async def cmd_kind(message: Message, services: Services, command: CommandObject) -> None:
    """نمای یک دسته با دستورهایی مانند /gold و /crypto."""
    name = (command.command or "").lower()
    kind = _KIND_COMMANDS.get(name)
    if kind is None:
        await message.answer(texts.render_error("دستهٔ ناشناخته"))
        return
    slugs = [a.slug for a in asset_registry.by_kind(kind)]
    await _send_market(message, services, slugs, kind.label)


async def cmd_price(message: Message, services: Services, command: CommandObject) -> None:
    """قیمت یک قلم؛ بدون آرگومان، فهرست شاخص‌ها."""
    query = (command.args or "").strip()
    if not query:
        await _send_market(message, services, list(asset_registry.FEATURED), "اقلام شاخص")
        return
    asset = asset_registry.search(query)
    if asset is None:
        await message.answer(texts.search_not_found(query), reply_markup=keyboards.market_keyboard())
        return
    await _send_quote(message, services, asset.slug)


async def _send_quote(message: Message, services: Services, slug: str, *, force: bool = False) -> None:
    """کارت یک قلم با کیبورد اکشن."""
    try:
        quote = await services.market.quote(slug, force=force)
    except PriceUnavailable as exc:
        await message.answer(texts.render_unavailable(exc.slugs, exc.detail))
        return
    user_id = message.from_user.id if message.from_user else 0
    in_watchlist = services.storage.watchlist.contains(user_id, slug) if user_id else False
    await message.answer(
        texts.render_price_card(quote),
        reply_markup=keyboards.price_detail_keyboard(slug, in_watchlist=in_watchlist),
    )


async def cmd_chart(message: Message, services: Services, command: CommandObject) -> None:
    """نمودار تاریخچهٔ یک قلم."""
    query = (command.args or "").strip()
    asset = asset_registry.search(query) if query else None
    if asset is None:
        await message.answer(texts.search_not_found(query or "—"))
        return
    await _send_chart(message, services, asset.slug)


async def _send_chart(message: Message, services: Services, slug: str, *, hours: int = 24) -> None:
    """رندر و ارسال نمودار؛ در نبود تاریخچه، پیام صادقانه."""
    points = services.storage.history.series(slug, hours=hours, limit=600)
    try:
        png = await render_price_chart_async(
            texts.title_of(slug), points, unit=asset_registry.ASSETS[slug].unit
        )
    except ChartUnavailable as exc:
        if exc.backend_missing:
            # مشکل موقتی نیست؛ صادقانه بگو که این نصب بدون نمودار است.
            await message.answer(
                "📈 موتور رسم نمودار روی این نصب فعال نیست، پس نمودار نمی‌توانم بسازم.\n"
                "بقیهٔ امکانات (قیمت، هشدار، دیده‌بان و تاریخچه) کامل کار می‌کند."
            )
            return
        await message.answer(
            f"📈 برای {texts.title_of(slug)} هنوز تاریخچهٔ کافی ندارم "
            f"({exc.have} نقطه از {exc.need} لازم).\n\n"
            "قیمت‌ها به‌مرور ثبت می‌شوند؛ چند دقیقه دیگر دوباره تلاش کنید. "
            "برای پر شدن سریع‌تر، /watchlist را روی این قلم تنظیم کنید."
        )
        return
    await message.answer_photo(
        BufferedInputFile(png, filename=f"{slug}.png"),
        caption=texts.render_chart_caption(slug, len(points), hours),
    )


# ------------------------------------------------------------------ callbacks
async def cb_market(callback: CallbackQuery, services: Services) -> None:
    slugs = list(asset_registry.FEATURED)
    for extra in ("geram24", "mesghal", "sekeb", "aed", "tether", "solana"):
        if extra not in slugs and asset_registry.exists(extra):
            slugs.append(extra)
    try:
        snapshot = await services.market.snapshot(slugs)
    except PriceUnavailable as exc:
        await callback.answer("داده در دسترس نیست", show_alert=True)
        _ = exc
        return
    missing = [s for s in slugs if s not in snapshot.quotes]
    text = texts.render_market(
        snapshot.quotes, title="نمای بازار", missing=missing, from_cache=snapshot.from_cache
    )
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=keyboards.market_keyboard())
        except Exception:  # noqa: BLE001
            await callback.message.answer(text, reply_markup=keyboards.market_keyboard())
    await callback.answer("به‌روزرسانی شد" if not snapshot.from_cache else "از کش")


async def cb_kind(callback: CallbackQuery, services: Services) -> None:
    name = (callback.data or "").split(":")[-1]
    kind = _KIND_COMMANDS.get(name)
    if kind is None:
        await callback.answer("دستهٔ ناشناخته", show_alert=True)
        return
    slugs = [a.slug for a in asset_registry.by_kind(kind)]
    try:
        snapshot = await services.market.snapshot(slugs)
    except PriceUnavailable:
        await callback.answer("داده در دسترس نیست", show_alert=True)
        return
    missing = [s for s in slugs if s not in snapshot.quotes]
    text = texts.render_market(snapshot.quotes, title=kind.label, missing=missing)
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=keyboards.kind_keyboard(kind))
        except Exception:  # noqa: BLE001
            await callback.message.answer(text, reply_markup=keyboards.kind_keyboard(kind))
    await callback.answer()


async def cb_price(callback: CallbackQuery, services: Services) -> None:
    slug = (callback.data or "").split(":", 1)[1]
    if not asset_registry.exists(slug):
        await callback.answer("قلم ناشناخته", show_alert=True)
        return
    try:
        quote = await services.market.quote(slug, force=True)
    except PriceUnavailable as exc:
        await callback.answer("داده در دسترس نیست", show_alert=True)
        log.warning("price callback unavailable: %s", exc.detail)
        return
    user_id = callback.from_user.id
    text = texts.render_price_card(quote)
    markup = keyboards.price_detail_keyboard(
        slug, in_watchlist=services.storage.watchlist.contains(user_id, slug)
    )
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except Exception:  # noqa: BLE001
            await callback.message.answer(text, reply_markup=markup)
    await callback.answer("به‌روزرسانی شد")


async def cb_chart(callback: CallbackQuery, services: Services) -> None:
    slug = (callback.data or "").split(":", 1)[1]
    if not asset_registry.exists(slug):
        await callback.answer("قلم ناشناخته", show_alert=True)
        return
    await callback.answer("در حال ساخت نمودار…")
    if callback.message is not None:
        await _send_chart(callback.message, services, slug)


def build_router() -> Router:
    """ساخت router تازهٔ دستورهای بازار."""
    router = Router(name="market")
    router.message.register(cmd_market, Command("market"))
    router.message.register(cmd_kind, Command(*_KIND_COMMANDS.keys()))
    router.message.register(cmd_price, Command("price"))
    router.message.register(cmd_chart, Command("chart"))
    router.callback_query.register(cb_market, F.data == "nav:market")
    router.callback_query.register(cb_kind, F.data.startswith("nav:kind:"))
    router.callback_query.register(cb_price, F.data.startswith("price:"))
    router.callback_query.register(cb_chart, F.data.startswith("chart:"))
    return router


__all__ = ["build_router", "_send_quote", "_send_market", "_send_chart"]
