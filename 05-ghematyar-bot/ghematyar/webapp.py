# -*- coding: utf-8 -*-
"""حالت webhook — وب‌سرور aiohttp برای تولید.

نقطه‌های پایانی:

* ``POST /tg-webhook`` — دریافت آپدیت‌های تلگرام (با هدر secret)
* ``GET /health`` — بررسی سلامت سرویس، شامل وضعیت منابع داده
* ``GET /`` — همان سلامت، برای بررسی سریع مرورگر
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from .bot.notifier import TelegramNotifier
from .config import Config
from .runtime import build_runtime, cleanup_webhook, on_webhook_startup
from .services import AlertMonitor, Services

log = logging.getLogger("ghematyar.webapp")


def create_web_app(config: Config, services: Services | None = None) -> web.Application:
    """ساخت اپلیکیشن aiohttp با ربات و پایشگر متصل."""
    bot, dispatcher, services = build_runtime(config, services)
    monitor = AlertMonitor(config, services.market, services.alerts, TelegramNotifier(bot))

    app = web.Application()
    app["bot"] = bot
    app["dispatcher"] = dispatcher
    app["services"] = services
    app["monitor"] = monitor
    app["monitor_task"] = None

    async def health(_request: web.Request) -> web.Response:
        """سلامت سرویس + وضعیت آخرین تلاش منابع."""
        cache_items, cache_age = services.market.cache_info()
        history = services.storage.history.stats()
        return web.json_response({
            "status": "ok",
            "service": "ghematyar-bot",
            "mode": "webhook",
            "engine_ready": True,
            "cache": {"items": cache_items, "age_seconds": round(cache_age, 1)},
            "history": history,
            "providers": [
                {
                    "name": status.name,
                    "ok": status.ok,
                    "latency_ms": status.latency_ms,
                    "items": status.items,
                    "error": status.error,
                }
                for status in services.market.provider_status()
            ],
        })

    async def on_startup(_app: web.Application) -> None:
        await on_webhook_startup(bot, config, dispatcher)
        app["monitor_task"] = asyncio.create_task(monitor.run(), name="alert-monitor")

    async def on_shutdown(_app: web.Application) -> None:
        monitor.stop()
        task = app["monitor_task"]
        if task is not None:
            task.cancel()
        await cleanup_webhook(bot, config)
        await services.close()
        await bot.session.close()

    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=config.telegram.webhook_secret,
    ).register(app, path=config.telegram.webhook_path)
    setup_application(app, dispatcher, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


def run_webhook(config: Config, services: Services | None = None) -> None:
    """اجرای وب‌سرور webhook (برای توسعهٔ محلی؛ در تولید gunicorn)."""
    app = create_web_app(config, services)
    web.run_app(app, host="0.0.0.0", port=config.telegram.port)


__all__ = ["create_web_app", "run_webhook"]
