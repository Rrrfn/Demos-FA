# -*- coding: utf-8 -*-
"""زمان‌بند — جمع‌آوری دوره‌ای در پس‌زمینه.

چرا نخ‌های ساده به‌جای کتابخانهٔ زمان‌بند: کار این سامانه دو حلقهٔ مستقل است
(جمع‌آوری و ارزیابی هشدار) و هر دو باید در تست‌ها قابل اجرای دستی باشند.
کتابخانهٔ بیرونی این‌جا ارزش افزوده‌ای ندارد و فقط یک وابستگی و یک منبع خطا
اضافه می‌کند.

سه محافظ تکرار:

* **قفل درون‌پروسه‌ای** — دو دور هرگز هم‌زمان اجرا نمی‌شوند.
* **قرارداد پایگاه داده** — در تعدد پروسه (چند worker) فقط یکی جمع می‌کند.
* **شروع با تأخیر** — حلقه بعد از بالا آمدن سرویس شروع می‌شود تا healthcheck
  پیش از همه‌چیز پاسخ بگیرد.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field

from .config import Config
from .services.alerts import AlertEngine
from .services.collector import CollectionResult, Collector
from .services.market import MarketService

log = logging.getLogger("cheshmbaz.scheduler")


@dataclass(slots=True)
class CycleReport:
    """حاصل یک دور کامل (جمع‌آوری + ارزیابی)."""

    started_at: float
    finished_at: float = 0.0
    collection: dict = field(default_factory=dict)
    alerts: dict = field(default_factory=dict)
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at or None,
            "duration_ms": int((self.finished_at - self.started_at) * 1000) if self.finished_at else 0,
            "skipped": self.skipped,
            "collection": self.collection,
            "alerts": self.alerts,
        }


class Scheduler:
    """زمان‌بند سبک با دو حلقهٔ مستقل."""

    def __init__(
        self,
        config: Config,
        collector: Collector,
        market: MarketService,
        engine: AlertEngine,
    ) -> None:
        self.config = config
        self.collector = collector
        self.market = market
        self.engine = engine
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._collect_lock = threading.Lock()
        self._alert_lock = threading.Lock()
        self.last_cycle: CycleReport | None = None
        self.cycles = 0

    # ---------------------------------------------------------------- control
    @property
    def is_running(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    def start(self) -> None:
        """راه‌اندازی حلقه‌ها — بی‌عارضه اگر از قبل اجرا شوند."""
        if self.is_running:
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._collection_loop, name="collector", daemon=True),
            threading.Thread(target=self._alert_loop, name="alerts", daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        log.info(
            "scheduler started: collect every %ds, evaluate every %ds",
            self.config.collector.interval_seconds, self.config.alerts.interval_seconds,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """توقف نرم."""
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads = []
        log.info("scheduler stopped")

    # ------------------------------------------------------------------ loops
    def _collection_loop(self) -> None:
        # تأخیر کوتاه تا سرویس وب پیش از اولین واکشی پاسخ بدهد
        if self._stop.wait(min(5.0, self._jitter(3.0))):
            return
        while not self._stop.is_set():
            try:
                self.run_cycle()
            except Exception:  # noqa: BLE001 - حلقه نباید بمیرد
                log.exception("collection cycle failed")
            interval = max(30, self.config.collector.interval_seconds)
            if self._stop.wait(interval + self._jitter(interval * 0.05)):
                return

    def _alert_loop(self) -> None:
        if self._stop.wait(min(10.0, self._jitter(5.0))):
            return
        while not self._stop.is_set():
            try:
                self.evaluate_alerts()
            except Exception:  # noqa: BLE001 - حلقه نباید بمیرد
                log.exception("alert cycle failed")
            interval = max(30, self.config.alerts.interval_seconds)
            if self._stop.wait(interval + self._jitter(interval * 0.05)):
                return

    @staticmethod
    def _jitter(seconds: float) -> float:
        """نوسان تصادفی تا دو نمونهٔ هم‌زمان دقیقاً روی هم نیفتند."""
        return random.uniform(0, max(0.0, seconds))

    # ------------------------------------------------------------------ cycle
    def run_cycle(self, *, use_lease: bool = True) -> CycleReport:
        """یک دور: جمع‌آوری، سپس ارزیابی هشدارها."""
        acquired = self._collect_lock.acquire(blocking=False)
        if not acquired:
            report = CycleReport(started_at=time.time(), skipped=True)
            report.finished_at = time.time()
            return report
        try:
            report = CycleReport(started_at=time.time())
            result: CollectionResult = self.collector.collect(use_lease=use_lease)
            report.collection = result.to_dict()
            if result.ok or result.quotes_saved:
                self.market.invalidate()
            outcome = self.engine.evaluate()
            report.alerts = outcome.to_dict()
            report.finished_at = time.time()
            self.last_cycle = report
            self.cycles += 1
            return report
        finally:
            self._collect_lock.release()

    def evaluate_alerts(self) -> dict:
        """ارزیابی مستقل هشدارها (بدون واکشی)."""
        if not self._alert_lock.acquire(blocking=False):
            return {"skipped": True, "reason": "ارزیابی دیگری در حال اجراست"}
        try:
            return self.engine.evaluate().to_dict()
        finally:
            self._alert_lock.release()

    def status(self) -> dict:
        """وضعیت زمان‌بند برای پنل."""
        return {
            "running": self.is_running,
            "cycles": self.cycles,
            "collect_interval_seconds": self.config.collector.interval_seconds,
            "alert_interval_seconds": self.config.alerts.interval_seconds,
            "last_cycle": self.last_cycle.to_dict() if self.last_cycle else None,
            "lease": self.collector.lease_holder(),
        }


__all__ = ["CycleReport", "Scheduler"]
