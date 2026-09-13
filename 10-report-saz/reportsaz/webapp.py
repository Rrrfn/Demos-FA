# -*- coding: utf-8 -*-
"""نقطهٔ ورود WSGI — همان چیزی که gunicorn وارد می‌کند.

    gunicorn reportsaz.webapp:app

ساخت برنامه در سطح ماژول انجام می‌شود چون سرور WSGI به یک شیء آماده نیاز
دارد، ولی خودِ ساخت در ``create_app`` است تا آزمون‌ها بتوانند نمونه‌های
مستقل بسازند و به وضعیت جهانی وابسته نباشند.
"""
from __future__ import annotations

import logging
import os

from .store import sweep
from .web import create_app

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = create_app()

#: پاک‌سازی بسته‌های منقضی در زمان بالا آمدن — نه در هر درخواست، چون پیمایش
#: دیسک روی هر صفحه هزینه دارد.
with app.app_context():
    try:
        _swept = sweep()
        logging.getLogger("reportsaz").info("پاک‌سازی آغازین: %s", _swept)
    except OSError as _error:                       # noqa: BLE001
        logging.getLogger("reportsaz").warning("پاک‌سازی آغازین انجام نشد: %s",
                                               _error)

__all__ = ["app"]
