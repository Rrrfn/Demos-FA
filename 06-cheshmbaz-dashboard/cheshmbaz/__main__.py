# -*- coding: utf-8 -*-
"""نقطهٔ ورود خط فرمان.

    python -m cheshmbaz serve     # اجرای محلی سرویس وب
    python -m cheshmbaz collect   # یک دور واکشی واقعی
    python -m cheshmbaz evaluate  # یک دور ارزیابی هشدار
    python -m cheshmbaz check     # آزمون زندهٔ منابع
    python -m cheshmbaz status    # وضعیت پایگاه داده
    python -m cheshmbaz init-db   # ساخت اسکیما و آینه‌سازی رجیستری

خروجی‌ها همیشه با ارقام فارسی چاپ می‌شوند و کنسول‌های غیر UTF-8 ویندوز هم
مدیریت می‌شوند تا اجرای دستور با سقوط رمزگذاری شکست نخورد.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import replace

from .assets import all_assets_ordered
from .config import load_config
from .context import AppContext
from .core.formatting import fa_clock, fa_duration, fa_number, fa_percent, fa_price

log = logging.getLogger("cheshmbaz.cli")


def _configure_console() -> None:
    """اجبار کنسول به UTF-8 تا چاپ فارسی روی ویندوز نشکند."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# ------------------------------------------------------------------- commands
def cmd_serve(args: argparse.Namespace) -> int:
    """اجرای سرویس وب روی سرور توسعه."""
    from .webapp import create_app

    config = load_config()
    if args.port:
        config = config.retuned(port=int(args.port))
    if args.no_collector:
        config = replace(config, collector=replace(config.collector, enabled=False))
    context = AppContext.build(config)
    context.bootstrap()
    app = create_app(context)
    print(f"cheshmbaz روی http://127.0.0.1:{config.port} بالا آمد ({config.env})")
    app.run(host="0.0.0.0", port=config.port, debug=not config.is_production, use_reloader=False)
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    """یک دور جمع‌آوری واقعی و چاپ گزارش."""
    config = load_config()
    context = AppContext.build(config)
    context.storage_ready()
    result = context.collector.collect(use_lease=not args.force)
    payload = result.to_dict()

    print(f"دور جمع‌آوری — {fa_clock()} ({fa_number(payload['duration_ms'])} میلی‌ثانیه)")
    for run in payload["providers"]:
        state = "سالم" if run["ok"] else "خطا"
        line = (
            f"  {run['name']}: {state} — "
            f"{fa_number(run['received'])}/{fa_number(run['requested'])} قلم"
        )
        if run["latency_ms"]:
            line += f" در {fa_number(run['latency_ms'])} میلی‌ثانیه"
        if run["missing"]:
            line += f" | غایب: {', '.join(run['missing'])}"
        if run["error"]:
            line += f" | {run['error']}"
        print(line)
    print(
        f"  ثبت‌شده: {fa_number(payload['quotes_saved'])} قیمت، "
        f"{fa_number(payload['readings_saved'])} نمونهٔ تاریخچه، "
        f"{fa_number(payload['with_change'])} تغییر محاسبه‌شده"
    )
    if payload["skipped"]:
        print(f"  رد شد: {payload['reason']}")
    return 0 if payload["ok"] or payload["quotes_saved"] else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    """یک دور ارزیابی هشدار."""
    config = load_config()
    context = AppContext.build(config)
    context.storage_ready()
    payload = context.engine.evaluate().to_dict()
    print(
        f"ارزیابی هشدار — بررسی: {fa_number(payload['checked'])}، "
        f"آگاه‌سازی: {fa_number(payload['notified'])}، "
        f"مهارشده: {fa_number(payload['suppressed'])}"
    )
    for event in payload["events"]:
        print(f"  ▲ {event['message']}")
    for event in payload["suppressed_events"]:
        print(f"  · مهار شد: {event['message']} ({event['reason']})")
    if payload["skipped_stale"]:
        print(f"  دادهٔ کهنه (بدون ارزیابی): {', '.join(sorted(set(payload['skipped_stale'])))}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """آزمون زندهٔ منابع — شفاف و بدون عدد ساختگی."""
    config = load_config()
    context = AppContext.build(config)
    context.storage_ready()
    result = context.collector.collect(use_lease=True)
    quotes = context.storage.quotes.all()

    print(f"آزمون زندهٔ منابع — {fa_clock()}")
    print("-" * 62)
    covered = 0
    for asset in all_assets_ordered():
        quote = quotes.get(asset.slug)
        if quote is None:
            print(f"  {asset.title:<22} — در دسترس نیست")
            continue
        covered += 1
        change = fa_percent(quote.change_pct) if quote.change_pct is not None else "—"
        print(
            f"  {asset.title:<22} {fa_price(quote.price, quote.unit, asset.precision):>22}"
            f"  {change:>9}  {fa_duration(quote.age_seconds)}"
        )
    print("-" * 62)
    for run in result.to_dict()["providers"]:
        state = "سالم" if run["ok"] else "خطا"
        print(f"  منبع {run['name']}: {state} ({fa_number(run['received'])} قلم)")
    total = len(all_assets_ordered())
    print(f"  پوشش: {fa_number(covered)}/{fa_number(total)}")
    return 0 if covered else 1


def cmd_status(args: argparse.Namespace) -> int:
    """وضعیت پایگاه داده و منابع."""
    config = load_config()
    context = AppContext.build(config)
    context.storage_ready()
    stats = context.storage.stats()
    print(f"پایگاه داده: {stats['path']}")
    print(f"  نسخهٔ اسکیما: {fa_number(stats['schema_version'])}")
    print(f"  قیمت‌های ذخیره‌شده: {fa_number(stats['quotes'])}")
    print(f"  نمونه‌های تاریخچه: {fa_number(stats['readings'])}")
    print(f"  قواعد هشدار: {fa_number(stats['alert_rules'])}")
    print(f"  رخدادهای هشدار: {fa_number(stats['alert_events'])}")
    print(f"  حجم فایل: {fa_number(stats['size_bytes'] / 1024, 1)} کیلوبایت")
    if stats["newest_reading"]:
        print(f"  تازه‌ترین نمونه: {fa_clock(stats['newest_reading'])}")
    for status in context.storage.sources.latest():
        state = "سالم" if status.ok else "خطا"
        age = time.time() - status.checked_at if status.checked_at else None
        detail = f"در {fa_number(status.latency_ms)} میلی‌ثانیه" if status.latency_ms else "—"
        line = f"  منبع {status.name}: {state} — آخرین بررسی {fa_duration(age)} ({detail})"
        if status.error:
            line += f" | {status.error}"
        print(line)
    return 0


def cmd_init_db(args: argparse.Namespace) -> int:
    """ساخت اسکیما و آینه‌سازی رجیستری دارایی‌ها."""
    from .services.collector import seed_registry

    config = load_config()
    context = AppContext.build(config)
    context.storage_ready()
    seed_registry(context.storage)
    print(f"اسکیما آماده است (نسخهٔ {fa_number(context.storage.schema_version())})")
    print(f"{fa_number(len(all_assets_ordered()))} دارایی در پایگاه داده آینه شد")
    return 0


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    """ساخت پارسر خط فرمان."""
    parser = argparse.ArgumentParser(
        prog="python -m cheshmbaz",
        description="چشم‌باز — داشبورد هوشمند بازار",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="لاگ کامل")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="اجرای سرویس وب محلی")
    serve.add_argument("--port", type=int, default=0, help="درگاه (پیش‌فرض از محیط)")
    serve.add_argument("--no-collector", action="store_true", help="بدون جمع‌آوری دوره‌ای")
    serve.set_defaults(func=cmd_serve)

    collect = sub.add_parser("collect", help="یک دور واکشی واقعی")
    collect.add_argument("--force", action="store_true", help="نادیده‌گرفتن قرارداد جمع‌آوری")
    collect.set_defaults(func=cmd_collect)

    evaluate = sub.add_parser("evaluate", help="یک دور ارزیابی هشدار")
    evaluate.set_defaults(func=cmd_evaluate)

    check = sub.add_parser("check", help="آزمون زندهٔ منابع")
    check.set_defaults(func=cmd_check)

    status = sub.add_parser("status", help="وضعیت پایگاه داده")
    status.set_defaults(func=cmd_status)

    init_db = sub.add_parser("init-db", help="ساخت اسکیما و آینه‌سازی رجیستری")
    init_db.set_defaults(func=cmd_init_db)

    return parser


def main(argv: list[str] | None = None) -> int:
    """اجرای خط فرمان."""
    _configure_console()
    args = build_parser().parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
