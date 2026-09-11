# -*- coding: utf-8 -*-
"""پایشگر پس‌زمینه — حلقهٔ بررسی هشدارها و ارسال اعلان.

این لایه آگاهانه به تلگرام وابسته نیست: ارسال از راه ``Notifier`` تزریق
می‌شود. در نتیجه کل چرخهٔ «شرط برقرار شد → اعلان رفت» بدون شبکه و بدون
ربات واقعی قابل تست است، و در تولید همان کد با یک Notifier تلگرامی کار
می‌کند.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

from ..config import Config
from ..core.errors import PriceUnavailable
from ..core.models import Quote
from ..storage import Alert
from .alerts import AlertService
from .market import MarketService

log = logging.getLogger("ghematyar.monitor")


class Notifier(Protocol):
    """قرارداد ارسال اعلان."""

    async def send(self, alert: Alert, quote: Quote) -> None:
        """اعلان را می‌فرستد؛ در خطا استثنا بالا می‌رود."""
        ...


@dataclass(slots=True)
class MonitorResult:
    """خلاصهٔ یک دور پایش."""

    checked: int = 0
    matched: int = 0
    sent: int = 0
    suppressed: int = 0
    failed: int = 0
    unavailable: bool = False
    skipped_reasons: dict[str, int] = field(default_factory=dict)

    def note(self, reason: str) -> None:
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1


class AlertMonitor:
    """حلقهٔ پایش هشدارها."""

    def __init__(
        self,
        config: Config,
        market: MarketService,
        alerts: AlertService,
        notifier: Notifier,
    ) -> None:
        self.config = config
        self.market = market
        self.alerts = alerts
        self.notifier = notifier
        self._stop = asyncio.Event()
        self._last_maintenance = 0.0

    # -------------------------------------------------------------------- loop
    async def run(self) -> None:
        """چرخهٔ بی‌پایان پایش — با خطای مهارشده در هر دور."""
        interval = self.config.alerts.interval
        log.info("alert monitor started (interval %ds)", interval)
        # کمی صبر تا ربات و منابع آماده شوند
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=10)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                result = await self.check_once()
                if result.checked:
                    log.info(
                        "monitor round: checked=%d sent=%d suppressed=%d failed=%d",
                        result.checked, result.sent, result.suppressed, result.failed,
                    )
                await self._maybe_maintenance()
            except Exception:  # noqa: BLE001
                log.exception("monitor round crashed; continuing")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        """توقف تمیز حلقه."""
        self._stop.set()

    # ------------------------------------------------------------------- round
    async def check_once(self) -> MonitorResult:
        """یک دور کامل: خواندن هشدارهای فعال، سنجش شرط و اعلان."""
        result = MonitorResult()
        watchable = self.alerts.alerts.list_watchable()
        if not watchable:
            return result

        slugs = sorted({a.slug for a in watchable})
        try:
            snapshot = await self.market.snapshot(slugs)
        except PriceUnavailable as exc:
            # نبود داده هرگز به اعلان ساختگی تبدیل نمی‌شود؛ فقط ثبت می‌شود.
            # تفکیک دو حالت برای عیب‌یابی مهم است: اگر منبع پاسخ داده ولی
            # قیمت این قلم را نداشته، مشکل «قلم» است نه «منبع».
            result.unavailable = True
            reachable = any(status.ok for status in self.market.provider_status())
            reason = "quote_unusable" if reachable else "prices_unavailable"
            log.warning("monitor skipped: %s", exc.detail or "prices unavailable")
            for alert in watchable:
                result.note(reason)
            return result

        for alert in watchable:
            result.checked += 1
            quote = snapshot.get(alert.slug)
            if quote is None or not quote.is_usable:
                result.note("quote_unusable")
                continue
            self.alerts.alerts.mark_evaluated(alert.id, quote.price)
            if not self.alerts.evaluate(alert, quote):
                continue
            result.matched += 1

            decision = self.alerts.decide_notification(alert, quote)
            if not decision.allowed:
                result.suppressed += 1
                result.note(decision.reason)
                self.alerts.record_suppressed(alert, quote, decision)
                continue

            try:
                await self.notifier.send(alert, quote)
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                log.warning("notify failed for alert #%d: %s", alert.id, exc)
                status = self.alerts.record_failure(alert, str(exc))
                if status is not None:
                    log.warning("alert #%d disabled after repeated failures", alert.id)
                continue

            result.sent += 1
            self.alerts.record_triggered(alert, quote)
            log.info("alert #%d fired for user %d at %.2f", alert.id, alert.user_id, quote.price)

        return result

    # ------------------------------------------------------------- maintenance
    async def _maybe_maintenance(self) -> None:
        """پیرایش دوره‌ای تاریخچه و رویدادها (حداکثر هر ساعت یک‌بار)."""
        now = time.time()
        if now - self._last_maintenance < 3600:
            return
        self._last_maintenance = now
        try:
            history_removed = self.market.storage.history.prune(
                self.config.data.history_retention_days
            )
            events_removed = self.market.storage.events.prune(30)
            if history_removed or events_removed:
                log.info(
                    "maintenance pruned %d history points / %d events",
                    history_removed, events_removed,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("maintenance failed: %s", exc)


class CallbackNotifier:
    """Notifier سادهٔ مبتنی بر تابع — برای تست و سناریوهای سفارشی."""

    def __init__(self, callback) -> None:  # noqa: ANN001
        self.callback = callback
        self.sent: list[tuple[int, str]] = []

    async def send(self, alert: Alert, quote: Quote) -> None:
        result = self.callback(alert, quote)
        if asyncio.iscoroutine(result):
            await result
        self.sent.append((alert.id, alert.slug))


__all__ = ["AlertMonitor", "CallbackNotifier", "MonitorResult", "Notifier"]
