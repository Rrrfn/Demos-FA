# -*- coding: utf-8 -*-
"""اجرای محلی — همان برنامه‌ای که در تولید با gunicorn سرو می‌شود.

``wsgi.py`` نقطهٔ ورود سرور تولیدی است و مدل را پیش از نخستین درخواست گرم
می‌کند. این فایل برای توسعه است: سرور Flask با بازبارگذاری خودکار و بدون
گرم‌کردن اجباری مدل، تا هر تغییر کد سریع معلوم شود.

اجرا:
    python app.py                 # پورت ۵۰۰۰
    PORT=۸۰۰۰ python app.py       # پورت دلخواه
"""
from __future__ import annotations

import os
import sys

from hassanj.web import create_app

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main() -> None:
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "False")
    app = create_app()
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=debug)


if __name__ == "__main__":
    main()
