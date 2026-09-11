# -*- coding: utf-8 -*-
"""آداپتور اجرا از ریشهٔ پروژه: ``python webapp.py``.

این فایل فقط اپلیکیشن aiohttp را از ``ghematyar.webapp`` بیرون می‌دهد تا
اجرا از ریشهٔ پروژه ساده بماند. منطق هیچ‌جا این‌طرف نیست.

نکتهٔ مهم: اپلیکیشن aiohttp یک شیء WSGI یا ASGI نیست، پس زیر gunicorn اجرا
نمی‌شود و با اولین درخواست خطا می‌دهد. برای تولید از وب‌سرور خود aiohttp
استفاده کنید:

    python -m ghematyar webhook

تنها یک نمونهٔ سرویس کافی است: پایشگر هشدار یک‌بار در هر فرآیند اجرا
می‌شود؛ با چند نمونهٔ هم‌زمان، هر کدام جداگانه پایش می‌کرد.
"""
from __future__ import annotations

import logging

from ghematyar.config import load_config
from ghematyar.webapp import create_web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

config = load_config()
config.ensure_dirs()

app = create_web_app(config)

if __name__ == "__main__":  # اجرای محلی همین فایل هم ممکن است
    from aiohttp import web

    web.run_app(app, host="0.0.0.0", port=config.telegram.port)
