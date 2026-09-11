# -*- coding: utf-8 -*-
"""نقطهٔ ورود استاندارد: ``python -m ghematyar [mode]``.

حالت‌ها:

* ``polling`` (پیش‌فرض) — توسعهٔ محلی، بدون دامنه و SSL
* ``webhook`` — اجرای وب‌سرور aiohttp برای تولید
* ``check`` — آزمون زندهٔ منابع داده بدون نیاز به توکن تلگرام
* ``init-db`` — ساخت پایگاه داده و نمایش وضعیت آن

این فایل هیچ وابستگی به محل اجرا ندارد؛ importها مطلق و پکیجی‌اند، پس
``python -m ghematyar`` از هر مسیری کار می‌کند (و دیگر خطای
«attempted relative import with no known parent package» رخ نمی‌دهد).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import load_config


def _force_utf8_console() -> None:
    """جلوگیری از ``UnicodeEncodeError`` روی کنسول‌های غیر UTF-8.

    خروجی این ابزار فارسی است و نمادهایی مثل ✅ و ❌ دارد. کنسول پیش‌فرض
    ویندوز (مثلاً cp1256) نمی‌تواند این‌ها را رمزگذاری کند؛ بدون این تنظیم
    برنامه به‌جای نمایش پیام راهنما، با UnicodeEncodeError می‌افتد.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # جریانی که قابل تغییر نیست
            continue


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # کتابخانه‌های پرحرف را ساکت می‌کنیم
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def _run_check(config) -> int:
    """آزمون زندهٔ منابع — گزارش صادقانهٔ هر قلم و شکست‌ها."""
    from .core import assets as asset_registry
    from .core.errors import PriceUnavailable
    from .services import build_services

    services = build_services(config)
    print("=== آزمون زندهٔ منابع داده ===")
    print(f"پایگاه داده: {services.storage.path}")
    print(f"تعداد اقلام ثبت‌شده: {len(asset_registry.ASSETS)}")
    print()
    try:
        snapshot = await services.market.snapshot(force=True)
    except PriceUnavailable as exc:
        print(f"❌ هیچ داده‌ای دریافت نشد: {exc.detail or 'نامشخص'}")
        await services.close()
        return 1

    ok = 0
    print(f"{'قلم':<20} {'قیمت':>22}  {'منبع':<12} {'وضعیت'}")
    print("-" * 78)
    for slug in asset_registry.ASSETS:
        quote = snapshot.get(slug)
        if quote is None:
            print(f"{slug:<20} {'—':>22}  {'—':<12} بدون داده")
            continue
        ok += 1
        print(
            f"{slug:<20} {quote.price:>22,.2f}  {quote.source:<12} "
            f"{quote.freshness.value}"
        )
    print("-" * 78)
    print(f"موفق: {ok}/{len(asset_registry.ASSETS)}")
    print()
    print("وضعیت منابع:")
    for status in snapshot.statuses:
        mark = "🟢" if status.ok else "🔴"
        info = f"{status.items} قلم" if status.ok else status.error[:70]
        print(f"  {mark} {status.name}: {info} ({status.latency_ms}ms)")
    if snapshot.from_cache:
        print("  (پاسخ از کش کوتاه‌مدت)")

    history = services.storage.history.stats()
    print(f"\nتاریخچه: {history['points']} نقطه برای {history['assets']} قلم")
    await services.close()
    return 0 if ok > 0 else 1


def _run_init_db(config) -> int:
    """ساخت پایگاه داده و نمایش خلاصه."""
    from .storage import open_storage

    storage = open_storage(config.db_path)
    print(f"✅ پایگاه داده آماده است: {storage.path}")
    print(f"   هشدارها: {storage.alerts.count_live(0)} (این کاربر) ")
    print(f"   کاربران: {storage.users.count()}")
    storage.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """ورودی برنامه."""
    parser = argparse.ArgumentParser(
        prog="python -m ghematyar",
        description="قیمت‌یار — ربات پایش هوشمند بازار",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="polling",
        choices=("polling", "webhook", "check", "init-db"),
        help="حالت اجرا (پیش‌فرض: polling)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="لاگ کامل")
    # باید *پیش از* parse_args باشد: argparse متن راهنمای فارسی را چاپ
    # می‌کند و روی کنسول غیر UTF-8 می‌افتد.
    _force_utf8_console()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    config = load_config()
    config.ensure_dirs()

    if args.mode == "check":
        return asyncio.run(_run_check(config))
    if args.mode == "init-db":
        return _run_init_db(config)

    if not config.telegram.configured:
        print(
            "❌ متغیر TELEGRAM_TOKEN تنظیم نشده است.\n"
            "   توکن را از @BotFather بگیرید و سپس اجرا کنید:\n"
            "     export TELEGRAM_TOKEN=123456:ABC-DEF\n"
            "   راهنما: python -m ghematyar --help\n"
            "   برای آزمون داده‌ها بدون توکن: python -m ghematyar check"
        )
        return 2

    if args.mode == "webhook":
        from .webapp import run_webhook

        logging.getLogger("ghematyar").info("starting in webhook mode")
        run_webhook(config)
        return 0

    from .runtime import run_polling

    logging.getLogger("ghematyar").info("starting in polling mode")
    try:
        asyncio.run(run_polling(config))
    except (KeyboardInterrupt, SystemExit):
        print("\nخدانگهدار!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
