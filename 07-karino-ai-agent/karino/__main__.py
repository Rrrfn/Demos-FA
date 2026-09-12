# -*- coding: utf-8 -*-
"""نقطهٔ ورود استاندارد — ``python -m karino``.

سه فرمان دارد تا هم توسعه و هم تولید و هم بررسی سریع پوشش داده شود:

``serve`` (پیش‌فرض)  اجرای وب‌سرور، همراه با زمان‌بند پس‌زمینه.
``ingest``            یک دور جمع‌آوری و چاپ آمار، بدون بالا آوردن سرور.
``check``             بررسی سلامت: پایگاه داده، پروفایل و پاسخ منابع.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import get_settings


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S")


def cmd_serve(args) -> int:
    """اجرای وب‌سرور روی همان اپی که WSGI هم استفاده می‌کند.

    عمداً اپ تازه‌ای ساخته نمی‌شود: import همین ماژول از قبل یک اپ (و
    راه‌اندازی یک‌بارهٔ آن) ساخته است. ساخت اپ دوم، محافظ «یک‌بار در
    پروسه» را بی‌اثر جلوه می‌داد و زمان‌بند را هم دوباره روشن می‌کرد.
    """
    from .webapp import app as application

    settings = get_settings(refresh=True)
    if args.port:
        settings = _with_port(settings, args.port)
    application.config["KARINO_SETTINGS"] = settings

    if not args.scheduler:
        # زمان‌بند در راه‌اندازی module-level شروع شده است؛ اگر کاربر
        # خاموشی خواسته، همان را متوقف می‌کنیم — نه یک اپ تازه بدون آن.
        from .scheduler import shutdown as stop_scheduler

        stop_scheduler()

    host = args.host or "0.0.0.0"
    print(f"کارینو روی http://{host}:{settings.port} بالا آمد "
          f"(محیط: {settings.env}, زمان‌بند: {'روشن' if args.scheduler else 'خاموش'})")
    application.run(host=host, port=settings.port, debug=args.debug, use_reloader=False)
    return 0


def cmd_ingest(args) -> int:
    from .services.ingest import run_ingest

    stats = run_ingest(settings=get_settings(refresh=True))
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if stats.get("fetched") else 1


def cmd_check(args) -> int:
    """بررسی سریع پیش از ارائهٔ دمو."""
    from .profile import PORTFOLIO, SKILLS, TOTAL_WEIGHT
    from .pipeline.scoring import BUDGETS
    from .storage import database, init_db, jobs as jobs_repo

    settings = get_settings(refresh=True)
    settings.ensure_dirs()
    init_db()

    checks = {
        "env": settings.env,
        "db_path": database.db_path(),
        "skills": len(SKILLS),
        "total_weight": TOTAL_WEIGHT,
        "portfolio_projects": len(PORTFOLIO),
        "score_budget_total": sum(BUDGETS.values()),
        "stored_jobs": jobs_repo.count(),
        "scheduler_enabled": settings.enable_scheduler,
        "sources_enabled": settings.enabled_sources or "all",
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))

    problems = []
    if abs(sum(BUDGETS.values()) - 100) > 0.01:
        problems.append("مجموع سقف عامل‌های امتیازدهی ۱۰۰ نیست")
    if not SKILLS:
        problems.append("پروفایل مهارت خالی است")
    if problems:
        print("\nایرادها:")
        for problem in problems:
            print(" -", problem)
        return 1
    print("\nهمهٔ بررسی‌ها سالم است.")
    return 0


def _with_port(settings, port: int):
    from dataclasses import replace

    return replace(settings, port=port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="karino", description="کارینو — پلتفرم هوش استخدام")
    parser.add_argument("-v", "--verbose", action="store_true", help="لاگ کامل")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="اجرای وب‌سرور (پیش‌فرض)")
    serve.add_argument("--host", default="")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--debug", action="store_true")
    serve.add_argument("--no-scheduler", dest="scheduler", action="store_false", default=True)
    serve.set_defaults(func=cmd_serve)

    ingest = sub.add_parser("ingest", help="یک دور جمع‌آوری بدون سرور")
    ingest.set_defaults(func=cmd_ingest)

    check = sub.add_parser("check", help="بررسی سلامت پیکربندی و داده")
    check.set_defaults(func=cmd_check)

    # در نبود زیرفرمان، ``serve`` اجرا می‌شود؛ مقادیر زیر همان پیش‌فرض‌های
    # آن هستند تا نیازی به پارس دوباره نباشد (که پرچم‌ها را از دست می‌داد).
    parser.set_defaults(func=cmd_serve, host="", port=0, debug=False, scheduler=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
