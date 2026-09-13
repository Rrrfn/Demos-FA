# -*- coding: utf-8 -*-
"""اجرای بسته با ``python -m hassanj``.

همان کاری را می‌کند که ``python app.py``؛ این درگاه صرفاً یک راه ورود
استاندارد پایتون است تا کسی که مخزن را می‌خواند لازم نباشد بداند فایل اجرای
توسعه چه نامی دارد.
"""
from __future__ import annotations

import os

from .web import create_app


def main() -> None:
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "0") not in ("0", "false", "False")
    create_app().run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
