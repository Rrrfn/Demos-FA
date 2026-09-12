# -*- coding: utf-8 -*-
"""زمان‌بند پس‌زمینه — دورهای جمع‌آوری بدون وابستگی بیرونی.

عامداً یک ریسهٔ سادهٔ پایتون است، نه APScheduler: تنها کاری که لازم داریم
«هر N دقیقه یک تابع را اجرا کن» است، و یک ریسهٔ دیمن این کار را بدون
افزودن وابستگی و بدون چرخهٔ عمر پنهان انجام می‌دهد.

دو محافظ دارد:

* **تک‌نمونه‌ای:** دوبار فراخوانی ``start`` ریسهٔ دومی نمی‌سازد. این مهم
  است چون هم راه‌اندازی اپ و هم بارگذار مجدد می‌توانند صدا بزنند.
* **بدون همپوشانی:** اگر یک دور طول بکشد، دور بعدی پشت آن منتظر می‌ماند و
  هرگز دو دور هم‌زمان اجرا نمی‌شوند.
"""
from __future__ import annotations

import logging
import threading
import time

from .config import Settings, get_settings
from .core.text import fa_number
from .storage import activity

log = logging.getLogger("krn.scheduler")

_thread: threading.Thread | None = None
_stop = threading.Event()
_lock = threading.Lock()


def start(settings: Settings | None = None) -> bool:
    """شروع زمان‌بند. برگشت ``True`` اگر همین حالا روشن شد، ``False`` اگر از قبل روشن بود."""
    global _thread
    settings = settings or get_settings()

    with _lock:
        if _thread is not None and _thread.is_alive():
            return False

        _stop.clear()
        interval = max(5, settings.fetch_interval_min) * 60
        _thread = threading.Thread(
            target=_loop, args=(settings, interval),
            name="karino-scheduler", daemon=True)
        _thread.start()

    log.info("scheduler started: every %d min", settings.fetch_interval_min)
    activity.log("scheduler_started",
                 f"زمان‌بند فعال شد — جمع‌آوری هر {fa_number(settings.fetch_interval_min)} دقیقه",
                 level="info", meta={"interval_min": settings.fetch_interval_min})
    return True


def _loop(settings: Settings, interval: int) -> None:
    """حلقهٔ اصلی: خواب، سپس یک دور جمع‌آوری.

    تابع هرگز استثنا بیرون نمی‌دهد؛ خطای یک دور نباید ریسهٔ زمان‌بند را
    بکشد، وگرنه سامانه بی‌صدا از به‌روزرسانی می‌افتد.
    """
    while not _stop.wait(interval):
        try:
            from .services.ingest import run_ingest, score_pending

            run_ingest(settings=settings)
            score_pending()
        except Exception as exc:  # noqa: BLE001 — پایداری زمان‌بند مقدم است
            log.exception("scheduled ingest failed")
            activity.log("scheduler_error", f"دور زمان‌بندی‌شده شکست خورد — {exc}",
                         level="error")


def run_now(settings: Settings | None = None) -> dict:
    """اجرای فوری یک دور (برای دکمهٔ «جمع‌آوری» و تست دستی)."""
    from .services.ingest import run_ingest

    return run_ingest(settings=settings or get_settings())


def shutdown(timeout: float = 3.0) -> None:
    """توقف نرم — ریسه تا پایان کار جاری فرصت دارد."""
    global _thread
    _stop.set()
    thread = _thread
    if thread and thread.is_alive():
        thread.join(timeout=timeout)
    _thread = None
    log.info("scheduler stopped")


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def status() -> dict:
    settings = get_settings()
    return {
        "running": is_running(),
        "interval_min": settings.fetch_interval_min,
        "enabled": settings.enable_scheduler,
    }
