# -*- coding: utf-8 -*-
"""هندلرهای ربات — هر ماژول یک کارخانهٔ Router با یک مسئولیت.

هر ماژول به‌جای یک نمونهٔ سراسری، تابع ``build_router()`` دارد. این تابع هر بار
یک Router تازه می‌سازد؛ چون aiogram اجازه نمی‌دهد یک Router به دو Dispatcher
وصل شود، ساخت سراسری هندلرها برنامه را به «یک‌بار در هر پروسه» محدود می‌کرد.
"""
from . import alerts, common, fallback, market, watchlist

# ترتیب ساخت و ثبت در dispatcher؛ مسیر متن آزاد باید آخر بیاید
BUILDERS = (
    common.build_router,
    market.build_router,
    alerts.build_router,
    watchlist.build_router,
    fallback.build_router,
)

__all__ = ["BUILDERS", "alerts", "common", "fallback", "market", "watchlist"]
