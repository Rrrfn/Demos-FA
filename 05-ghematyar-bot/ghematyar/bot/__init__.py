# -*- coding: utf-8 -*-
"""لایهٔ ربات — هندلرها، کیبوردها، متن‌ها و میان‌افزارها.

``build_dispatcher`` تنها جایی است که ترتیب ثبت هندلرها تعیین می‌شود و
همیشه routerهای تازه می‌سازد؛
این ترتیب مهم است:

1. میان‌افزارها (کاربر، سیل، خطا)
2. هندلرهای عمومی و دستورها
3. هندلرهای بازار، هشدار و دیده‌بان
4. در پایان، مسیر متن آزاد — تا هیچ‌وقت روی هندلرهای دقیق‌تر نیفتد
"""
from __future__ import annotations

from aiogram import Dispatcher

from ..config import Config
from ..services import Services
from .handlers import BUILDERS
from .middleware import ErrorMiddleware, FloodMiddleware, UserTouchMiddleware

# وابستگی‌هایی که با نام در هندلرها قابل استفاده‌اند
DEPENDENCY_KEYS = ("services", "config")


def build_dispatcher(config: Config, services: Services) -> Dispatcher:
    """ساخت Dispatcher با وابستگی‌های تزریق‌شده و هندلرهای ثبت‌شده."""
    dispatcher = Dispatcher()

    # تزریق وابستگی: هندلرها فقط با نام پارامتر به این‌ها دست می‌یابند
    dispatcher.workflow_data.update({"services": services, "config": config})

    # میان‌افزارها به ترتیب: کاربر، مهار سیل، مهار خطا (بیرونی‌ترین)
    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.middleware(UserTouchMiddleware(services))
        observer.middleware(FloodMiddleware())
        observer.middleware(ErrorMiddleware())

    # ترتیب routers همان ترتیب اولویت تطبیق است. هر فراخوانی routerهای
    # تازه می‌سازد تا یک Dispatcher وابسته به وضعیت import نباشد.
    for build_router in BUILDERS:
        dispatcher.include_router(build_router())
    return dispatcher


__all__ = ["build_dispatcher", "DEPENDENCY_KEYS"]
