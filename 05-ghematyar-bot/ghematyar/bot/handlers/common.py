# -*- coding: utf-8 -*-
"""دستورهای عمومی: شروع، راهنما، دربارهٔ داده‌ها و وضعیت منابع."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ...core.errors import PriceUnavailable, UnknownAsset
from ...services import MarketService, Services
from .. import keyboards, texts

log = logging.getLogger("ghematyar.handlers.common")


async def cmd_start(message: Message, services: Services) -> None:
    """شروع + ثبت کاربر."""
    if message.from_user is not None:
        services.storage.users.touch(message.from_user.id, message.chat.id)
    await message.answer(
        texts.render_welcome(message.from_user.first_name if message.from_user else None),
        reply_markup=keyboards.main_menu(),
    )


async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=keyboards.main_menu())


async def cmd_about(message: Message) -> None:
    await message.answer(texts.ABOUT, reply_markup=keyboards.back_to_menu())


async def cmd_status(message: Message, services: Services) -> None:
    """وضعیت منابع داده، کش و تاریخچه."""
    # یک درخواست سبک تا وضعیت منابع واقعاً به‌روز شود
    try:
        await services.market.snapshot(["usd", "bitcoin"], force=True)
    except PriceUnavailable as exc:
        log.warning("status probe failed: %s", exc.detail)
    except UnknownAsset:
        pass

    cache_items, cache_age = services.market.cache_info()
    await message.answer(
        texts.render_status(
            services.market.provider_status(),
            cache_items,
            cache_age,
            services.storage.history.stats(),
        ),
        reply_markup=keyboards.back_to_menu(),
    )


async def cb_menu(callback: CallbackQuery, services: Services) -> None:
    await _edit_or_send(callback, texts.render_welcome(), keyboards.main_menu())
    await callback.answer()


async def cb_status(callback: CallbackQuery, services: Services) -> None:
    try:
        await services.market.snapshot(["usd", "bitcoin"], force=True)
    except PriceUnavailable:
        pass
    cache_items, cache_age = services.market.cache_info()
    await _edit_or_send(
        callback,
        texts.render_status(
            services.market.provider_status(),
            cache_items,
            cache_age,
            services.storage.history.stats(),
        ),
        keyboards.back_to_menu(),
    )
    await callback.answer()


async def _edit_or_send(callback: CallbackQuery, text: str, markup=None) -> None:
    """ویرایش پیام قبلی و در صورت نبود پیام، ارسال تازه."""
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001 - پیام یکسان یا غیرقابل‌ویرایش
        await callback.message.answer(text, reply_markup=markup)


def build_router() -> Router:
    """ساخت router تازهٔ دستورهای عمومی.

    هر Dispatcher router مستقل خود را می‌سازد. ثبت هندلرها در زمان import
    انجام نمی‌شود تا ساخت چندبارهٔ برنامه در یک پروسه (تست، وب‌سرور،
    جابه‌جایی بین حالت polling و webhook) خطای «router از قبل وصل شده»
    ندهد.
    """
    router = Router(name="common")
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_about, Command("about"))
    router.message.register(cmd_status, Command("status"))
    router.callback_query.register(cb_menu, F.data == "nav:menu")
    router.callback_query.register(cb_status, F.data == "nav:status")
    return router


__all__ = ["build_router", "_edit_or_send"]
