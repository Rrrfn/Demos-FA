# -*- coding: utf-8 -*-
"""اجرای برنامه — ساخت ربات، حالت polling و حالت webhook.

تفکیک دو حالت:

* **polling** برای توسعهٔ محلی: بدون دامنه، بدون SSL، بدون تنظیم webhook.
* **webhook** برای تولید: یک وب‌سرور aiohttp که آپدیت‌ها را از تلگرام
  می‌گیرد و همان Dispatcher را تغذیه می‌کند.

هر دو حالت پایشگر هشدار را در پس‌زمینه اجرا می‌کنند، پس رفتار محصول
یکسان است.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .bot import build_dispatcher
from .bot.notifier import TelegramNotifier
from .config import Config
from .services import AlertMonitor, Services, build_services

log = logging.getLogger("ghematyar.runtime")


def build_bot(config: Config) -> Bot:
    """ساخت نمونهٔ Bot با تنظیمات مشترک."""
    if not config.telegram.token:
        raise SystemExit(
            "TELEGRAM_TOKEN تنظیم نشده است.\n"
            "توکن را از @BotFather بگیرید و اجرا کنید:\n"
            "  export TELEGRAM_TOKEN=123456:ABC-DEF   (لینوکس/مک)\n"
            "  set TELEGRAM_TOKEN=123456:ABC-DEF      (ویندوز CMD)\n"
            '  $env:TELEGRAM_TOKEN="123456:ABC-DEF"   (پاورشل)'
        )
    return Bot(
        token=config.telegram.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_runtime(config: Config, services: Services | None = None) -> tuple[Bot, Dispatcher, Services]:
    """ساخت ربات، dispatcher و سرویس‌ها برای هر دو حالت اجرا."""
    services = services or build_services(config)
    bot = build_bot(config)
    dispatcher = build_dispatcher(config, services)
    return bot, dispatcher, services


async def run_polling(config: Config, services: Services | None = None) -> None:
    """اجرای ربات در حالت polling (توسعهٔ محلی)."""
    bot, dispatcher, services = build_runtime(config, services)
    monitor = AlertMonitor(
        config, services.market, services.alerts, TelegramNotifier(bot)
    )
    monitor_task = asyncio.create_task(monitor.run(), name="alert-monitor")
    try:
        # در polling هیچ webhook ثبت‌شده‌ای نباید مزاحم باشد
        await bot.delete_webhook(drop_pending_updates=True)
        me = await bot.get_me()
        log.info("polling started as @%s", me.username)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        monitor.stop()
        monitor_task.cancel()
        await services.close()
        await bot.session.close()


async def on_webhook_startup(bot: Bot, config: Config, dispatcher: Dispatcher) -> None:
    """ثبت webhook در تلگرام هنگام بالا آمدن سرور."""
    url = config.telegram.webhook_url
    if not url:
        log.warning(
            "RENDER_EXTERNAL_URL/WEBHOOK_BASE_URL تنظیم نشده است؛ "
            "webhook ثبت نشد و آپدیت‌ها دریافت نمی‌شوند."
        )
        return
    await bot.set_webhook(
        url,
        secret_token=config.telegram.webhook_secret,
        drop_pending_updates=True,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )
    log.info("webhook registered at %s", url)


async def cleanup_webhook(bot: Bot, config: Config) -> None:
    """حذف webhook هنگام خاموشی تا polling محلی بعداً کار کند."""
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("webhook removed on shutdown")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not remove webhook: %s", exc)


__all__ = [
    "build_bot",
    "build_runtime",
    "cleanup_webhook",
    "on_webhook_startup",
    "run_polling",
]
