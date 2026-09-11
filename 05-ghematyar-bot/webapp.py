# -*- coding: utf-8 -*-
"""نقطهٔ ورود تولید برای gunicorn: ``gunicorn webapp:app``.

این فایل فقط یک آداپتور است: منطق در ``ghematyar.webapp`` زندگی می‌کند.
هدف این است که فرمان تولید ساده بماند و import از ریشهٔ پروژه کار کند:

    gunicorn webapp:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 90

یک worker کافی است چون پایشگر هشدار یک‌بار در فرآیند اجرا می‌شود؛ با چند
worker، هر worker جداگانه پایش می‌کرد و همان هشدار چند بار بررسی می‌شد.
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
