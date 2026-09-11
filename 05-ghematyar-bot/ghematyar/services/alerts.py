# -*- coding: utf-8 -*-
"""سرویس هشدار — سیاست ساخت، ارزیابی و اجازهٔ اعلان.

مسیر کامل: کاربر → قلم → شرط → آستانه → پایشگر پس‌زمینه → اعلان.

سیاست‌های اعمال‌شده در همین لایه:

* **بدون تکرار** — هشدار یکسان دوباره ساخته نمی‌شود.
* **سقف تعداد** — تعداد هشدارهای زندهٔ هر کاربر محدود است.
* **ضد سیل** — یک قلم بیشتر از هر ``notify_cooldown`` اعلان نمی‌دهد و هر
  کاربر در ساعت سقف اعلان دارد.
* **یک‌بار مصرف اختیاری** — هشدار می‌تواند پس از اجرا خاموش شود یا فعال بماند.
* **وضعیت فعال/غیرفعال** — کاربر می‌تواند هشدار را موقتاً خاموش کند.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ..config import Config
from ..core.errors import (
    AlertLimitReached,
    AlertNotFound,
    DuplicateAlert,
)
from ..core.models import Quote
from ..storage import Alert, AlertDirection, AlertEventRepository, AlertRepository, AlertStatus
from ..storage.watchlist import UserRepository

log = logging.getLogger("ghematyar.alerts")


@dataclass(slots=True)
class NotificationDecision:
    """نتیجهٔ تصمیم دربارهٔ ارسال اعلان."""

    allowed: bool
    reason: str = ""      # کد دلیل در صورت رد
    detail: str = ""


class AlertService:
    """سیاست هشدارها — تنها مسیر مجاز برای ساخت و اعلان."""

    def __init__(
        self,
        config: Config,
        alerts: AlertRepository,
        events: AlertEventRepository,
        users: UserRepository,
    ) -> None:
        self.config = config
        self.alerts = alerts
        self.events = events
        self.users = users

    # ----------------------------------------------------------------- create
    def create(
        self,
        user_id: int,
        slug: str,
        direction: AlertDirection,
        target: float,
        *,
        one_shot: bool = True,
        cooldown_seconds: int | None = None,
    ) -> Alert:
        """ساخت هشدار با اعمال سیاست‌ها و ثبت رویداد."""
        cooldown = (
            self.config.alerts.notify_cooldown if cooldown_seconds is None else cooldown_seconds
        )
        alert = self.alerts.create(
            user_id, slug, direction, target,
            one_shot=one_shot,
            cooldown_seconds=cooldown,
            limit=self.config.alerts.max_per_user,
        )
        self.events.add(
            user_id, slug, "created", alert_id=alert.id, target=target,
            detail=f"{direction.value} {target:g}",
        )
        return alert

    def update_target(self, user_id: int, alert_id: int, target: float) -> Alert:
        alert = self.alerts.update(alert_id, user_id, target=target)
        self.events.add(
            user_id, alert.slug, "updated", alert_id=alert.id, target=target,
            detail=f"target={target:g}",
        )
        return alert

    # ---------------------------------------------------------------- manage
    def list(self, user_id: int) -> list[Alert]:
        return self.alerts.list_for_user(user_id)

    def get(self, user_id: int, alert_id: int) -> Alert:
        alert = self.alerts.get(alert_id, user_id)
        if alert is None:
            raise AlertNotFound(alert_id)
        return alert

    def toggle(self, user_id: int, alert_id: int) -> Alert:
        """خاموش/روشن کردن هشدار."""
        alert = self.alerts.toggle_paused(alert_id, user_id)
        if alert is None:
            raise AlertNotFound(alert_id)
        self.events.add(
            user_id, alert.slug, "updated", alert_id=alert.id,
            detail=f"status={alert.status.value}",
        )
        return alert

    def remove(self, user_id: int, alert_id: int) -> bool:
        alert = self.alerts.get(alert_id, user_id)
        if alert is None:
            raise AlertNotFound(alert_id)
        removed = self.alerts.delete(alert_id, user_id)
        if removed:
            self.events.add(user_id, alert.slug, "deleted", alert_id=alert_id,
                            detail="removed by user")
        return removed

    def clear(self, user_id: int) -> int:
        count = self.alerts.delete_all(user_id)
        if count:
            self.events.add(user_id, "*", "deleted", detail=f"cleared {count} alerts")
        return count

    def usage(self, user_id: int) -> tuple[int, int]:
        """(تعداد هشدار زنده، سقف مجاز)."""
        return self.alerts.count_live(user_id), self.config.alerts.max_per_user

    # ------------------------------------------------------------- evaluation
    def evaluate(self, alert: Alert, quote: Quote | None) -> bool:
        """آیا شرط هشدار با قیمت فعلی برقرار است؟"""
        if quote is None or not quote.is_usable:
            return False
        return alert.matches(quote.price)

    def decide_notification(
        self, alert: Alert, quote: Quote, *, now: float | None = None
    ) -> NotificationDecision:
        """آیا اجازهٔ ارسال اعلان برای این هشدار داریم؟

        ترتیب بررسی از ارزان به گران است و هر رد، دلیل صریح دارد تا در
        گزارش رویدادها قابل ردیابی باشد.
        """
        now = now if now is not None else time.time()
        if not alert.watchable:
            return NotificationDecision(False, "status", alert.status.value)
        if not self.users.notifications_enabled(alert.user_id):
            return NotificationDecision(False, "user_muted", "notifications disabled")
        if not quote.is_usable:
            return NotificationDecision(False, "unusable_quote", quote.freshness.value)

        # فاصلهٔ اعلان برای همین قلم (ضد تکرار پیام پشت‌سرهم)
        cooldown = alert.cooldown_seconds or self.config.alerts.notify_cooldown
        last_at = alert.last_notified_at or 0.0
        if cooldown > 0 and now - last_at < cooldown:
            remaining = cooldown - (now - last_at)
            return NotificationDecision(False, "cooldown", f"{remaining:.0f}s")

        # سقف ساعتی هر کاربر
        hour_ago = now - 3600
        sent_last_hour = self.events.count_since(alert.user_id, hour_ago)
        if sent_last_hour >= self.config.alerts.max_notifications_per_hour:
            return NotificationDecision(False, "hourly_cap", str(sent_last_hour))

        return NotificationDecision(True)

    def record_triggered(self, alert: Alert, quote: Quote) -> None:
        """ثبت اعلان موفق."""
        self.alerts.mark_notified(
            alert.id, quote.price, one_shot=alert.one_shot
        )
        self.events.add(
            alert.user_id, alert.slug, "triggered", alert_id=alert.id,
            price=quote.price, target=alert.target,
            detail=alert.direction.value,
        )

    def record_suppressed(self, alert: Alert, quote: Quote, decision: NotificationDecision) -> None:
        """ثبت اینکه شرط برقرار بود ولی اعلان ارسال نشد."""
        self.events.add(
            alert.user_id, alert.slug, "suppressed", alert_id=alert.id,
            price=quote.price, target=alert.target,
            detail=f"{decision.reason}:{decision.detail}",
        )

    def record_failure(self, alert: Alert, error: str) -> AlertStatus | None:
        """ثبت خطای ارسال؛ ممکن است به غیرفعال‌شدن هشدار منجر شود."""
        status = self.alerts.mark_failed(
            alert.id, disable_after=self.config.alerts.disable_after_failures
        )
        self.events.add(
            alert.user_id, alert.slug, "error", alert_id=alert.id,
            detail=error[:200],
        )
        return status

    def recent_events(self, user_id: int, limit: int = 15) -> list:
        return self.events.list_recent(user_id, limit)


__all__ = ["AlertService", "NotificationDecision", "AlertLimitReached", "DuplicateAlert"]
