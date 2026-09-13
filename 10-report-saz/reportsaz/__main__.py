# -*- coding: utf-8 -*-
"""اجرای سرویس با ``python -m reportsaz``.

اجرای مستقیم فایل (``python reportsaz/app.py``) شکسته است چون بسته در
``sys.path`` قرار نمی‌گیرد و importهای نسبی کار نمی‌کنند. این نقطهٔ ورود آن
مشکل را معماری حل می‌کند: ماژول از درون بسته اجرا می‌شود.
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reportsaz",
        description="گزارش‌ساز — سرویس گزارش‌سازی خودکار داده")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PORT", "10000")),
                        help="پورت سرویس (پیش‌فرض از متغیر محیطی PORT)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--production", action="store_true",
                        help="اجرای تولیدی بدون حالت اشکال‌زدایی")
    parser.add_argument("--sweep", action="store_true",
                        help="فقط پاک‌سازی بسته‌های منقضی و خروج")
    args = parser.parse_args(argv)

    from .store import sweep, usage

    if args.sweep:
        result = sweep(force=False)
        print(f"بسته‌های پاک‌شده: {result['removed']} — "
              f"نگه‌داشته‌شده: {result['kept']}")
        print(f"وضعیت دیسک: {usage()}")
        return 0

    from .web import create_app

    app = create_app()
    debug = not args.production
    print(f"گزارش‌ساز روی http://{args.host}:{args.port} بالا آمد "
          f"({'تولیدی' if args.production else 'توسعه'})")
    app.run(host=args.host, port=args.port, debug=debug, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
