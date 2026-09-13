# -*- coding: utf-8 -*-
"""نقطهٔ ورود توسعه.

    python app.py

برای استقرار، ``wsgi.py`` با gunicorn اجرا می‌شود؛ این فایل فقط برای اجرای
محلی و بازآزمایی خودکار است. سرور توسعهٔ Flask برای بار سنگین ساخته نشده،
پس اینجا فقط با آن کار می‌کنیم و در تولید از gunicorn استفاده می‌شود.
"""
from __future__ import annotations

import os

from khoneyab.web import create_app

app = create_app()


if __name__ == "__main__":
    # نسخه‌های کم‌حجم عکس‌ها در راه‌اندازی اول ساخته می‌شوند. این کار عمداً
    # اینجاست و نه در ``create_app``: خودِ البرنامه نباید به Pillow وابسته باشد
    # اگر کسی آن را درون یک فرایند دیگر سوار کند.
    from tools.make_thumbs import ensure_all

    stats = ensure_all()
    if stats:
        print(f"نسخه‌های کم‌حجم ساخته شد: {stats}")

    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8520")),
        debug=os.environ.get("FLASK_DEBUG", "") == "1",
        use_reloader=False,
    )
