# -*- coding: utf-8 -*-
"""هندلرهای دیده‌بان — فهرست اقلام مورد علاقهٔ کاربر."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...core import assets as asset_registry
from ...core.errors import PriceUnavailable
from ...services import Services
from .. import keyboards, texts

log = logging.getLogger("ghematyar.handlers.watchlist")


async def _render(message: Message, services: Services) -> None:
    """نمایش دیده‌بان با قیمت‌های تازه."""
    slugs = services.storage.watchlist.list_for_user(message.from_user.id)
    quotes: dict = {}
    if slugs:
        try:
            snapshot = await services.market.snapshot(slugs)
            quotes = snapshot.quotes
        except PriceUnavailable as exc:
            log.warning("watchlist quotes unavailable: %s", exc.detail)
    await message.answer(
        texts.render_watchlist(slugs, quotes, services.storage.watchlist.limit),
        reply_markup=keyboards.watchlist_keyboard(slugs),
    )


async def cmd_watchlist(message: Message, services: Services) -> None:
    await _render(message, services)


async def cb_watchlist(callback: CallbackQuery, services: Services) -> None:
    slugs = services.storage.watchlist.list_for_user(callback.from_user.id)
    quotes: dict = {}
    if slugs:
        try:
            snapshot = await services.market.snapshot(slugs)
            quotes = snapshot.quotes
        except PriceUnavailable:
            pass
    text = texts.render_watchlist(slugs, quotes, services.storage.watchlist.limit)
    markup = keyboards.watchlist_keyboard(slugs)
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except Exception:  # noqa: BLE001
            await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


async def cb_watch_add(callback: CallbackQuery, services: Services) -> None:
    slug = (callback.data or "").split(":", 1)[1]
    if not asset_registry.exists(slug):
        await callback.answer("قلم ناشناخته", show_alert=True)
        return
    user_id = callback.from_user.id
    if services.storage.watchlist.contains(user_id, slug):
        await callback.answer("از قبل در دیده‌بان است")
        return
    if not services.storage.watchlist.add(user_id, slug):
        await callback.answer(
            f"سقف دیده‌بان ({services.storage.watchlist.limit} قلم) پر است", show_alert=True
        )
        return
    await callback.answer(f"{texts.title_of(slug)} اضافه شد ⭐")


async def cb_watch_remove(callback: CallbackQuery, services: Services) -> None:
    slug = (callback.data or "").split(":", 1)[1]
    services.storage.watchlist.remove(callback.from_user.id, slug)
    await callback.answer(f"{texts.title_of(slug)} حذف شد")
    if callback.message is not None:
        slugs = services.storage.watchlist.list_for_user(callback.from_user.id)
        quotes: dict = {}
        if slugs:
            try:
                snapshot = await services.market.snapshot(slugs)
                quotes = snapshot.quotes
            except PriceUnavailable:
                pass
        try:
            await callback.message.edit_text(
                texts.render_watchlist(slugs, quotes, services.storage.watchlist.limit),
                reply_markup=keyboards.watchlist_keyboard(slugs),
            )
        except Exception:  # noqa: BLE001
            pass


def build_router() -> Router:
    """ساخت router تازهٔ دیده‌بان."""
    router = Router(name="watchlist")
    router.message.register(cmd_watchlist, Command("watchlist"))
    router.callback_query.register(cb_watchlist, F.data == "nav:watchlist")
    router.callback_query.register(cb_watch_add, F.data.startswith("watch:"))
    router.callback_query.register(cb_watch_remove, F.data.startswith("unwatch:"))
    return router


__all__ = ["build_router", "_render"]
