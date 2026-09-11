# -*- coding: utf-8 -*-
"""موتور هشدار — ارزیابی قواعد روی قیمت‌های واقعی.

چهار محافظ که از سیل هشدار جلوگیری می‌کنند:

۱. **قیمت نامعتبر، هشدار نمی‌سازد.** قاعده‌ای روی دادهٔ کهنه یا منقضی
   ارزیابی نمی‌شود؛ قیمت قدیمی نباید هشدار «الان» بدهد.
۲. **بازهٔ خنک‌شدن هر قاعده.** حتی اگر شرط برقرار بماند، در فاصلهٔ تعیین‌شده
   فقط یک آگاه‌سازی می‌رود.
۳. **سقف نرخ هر مالک.** بیش از چند رخداد در بازهٔ کوتاه ثبت نمی‌شود؛ بقیه
   «مهارشده» ثبت می‌شوند تا معلوم باشد چه اتفاقی افتاده.
۴. **قاعدهٔ یک‌باره** بعد از اولین وقوع خودکار متوقف می‌شود.

هر تلاش — موفق یا مهارشده — در دفتر رخداد می‌نشیند. پنهان‌کردن مهارشدن‌ها
باعث می‌شود کاربر فکر کند قاعده کار نمی‌کند.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..assets import ASSETS, get
from ..config import Config
from ..core.errors import ValidationError
from ..core.formatting import fa_number, fa_percent, fa_price
from ..core.models import AlertEvent, AlertKind, AlertRule, AlertStatus, Quote
from ..storage import Storage
from .market import MarketService

log = logging.getLogger("cheshmbaz.alerts")

#: سقف رخداد هر مالک در پنجرهٔ نرخ‌گذاری
RATE_WINDOW_SECONDS = 300
RATE_MAX_EVENTS = 12


@dataclass(slots=True)
class EvaluationOutcome:
    """حاصل یک دور ارزیابی."""

    checked: int = 0
    fired: list[AlertEvent] = field(default_factory=list)
    suppressed: list[AlertEvent] = field(default_factory=list)
    skipped_stale: list[str] = field(default_factory=list)
    skipped_missing: list[str] = field(default_factory=list)

    @property
    def notified(self) -> int:
        return len(self.fired)

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "notified": self.notified,
            "suppressed": len(self.suppressed),
            "skipped_stale": self.skipped_stale,
            "skipped_missing": self.skipped_missing,
            "events": [event.to_dict() for event in self.fired],
            "suppressed_events": [event.to_dict() for event in self.suppressed],
        }


class AlertEngine:
    """ارزیابی قواعد هشدار روی نقل‌قول‌های جاری."""

    def __init__(self, config: Config, storage: Storage, market: MarketService) -> None:
        self.config = config
        self.storage = storage
        self.market = market

    # ---------------------------------------------------------------- create
    def create(
        self,
        slug: str,
        kind: AlertKind,
        threshold: float,
        *,
        owner: str = "",
        one_shot: bool = False,
        cooldown_seconds: int | None = None,
        note: str = "",
    ) -> AlertRule:
        """ساخت قاعده با اعتبارسنجی کامل."""
        asset = get(slug)  # UnknownAsset اگر نباشد
        if kind is AlertKind.PCT_MOVE:
            if threshold <= 0:
                raise ValidationError("آستانهٔ نوسان درصدی باید بزرگ‌تر از صفر باشد", "threshold")
            if threshold > 1000:
                raise ValidationError("آستانهٔ نوسان درصدی بیش از حد بزرگ است", "threshold")
        else:
            if threshold <= 0:
                raise ValidationError("آستانهٔ قیمت باید بزرگ‌تر از صفر باشد", "threshold")
            # دارایی بدون اعشار نمی‌تواند آستانهٔ کسری داشته باشد
            if asset.precision == 0 and threshold < 1:
                raise ValidationError("آستانه برای این دارایی بسیار کوچک است", "threshold")

        if self.storage.alerts.count(owner=owner or None) >= self.config.alerts.max_rules:
            raise ValidationError(
                f"سقف قواعد هشدار ({fa_number(self.config.alerts.max_rules)}) پر شده است", "rules"
            )

        cooldown = (
            self.config.alerts.cooldown_seconds if cooldown_seconds is None else cooldown_seconds
        )
        return self.storage.alerts.add(
            slug, kind, threshold, owner=owner, one_shot=one_shot,
            cooldown_seconds=int(max(0, cooldown)), note=note,
        )

    # -------------------------------------------------------------- evaluate
    def evaluate(self, *, quotes: dict[str, Quote] | None = None) -> EvaluationOutcome:
        """یک دور ارزیابی همهٔ قواعد فعال."""
        outcome = EvaluationOutcome()
        rules = self.storage.alerts.active()
        if not rules:
            return outcome

        pool = quotes if quotes is not None else self.market.quotes()
        now = time.time()
        owner_counts: dict[str, int] = {}

        for rule in rules:
            outcome.checked += 1
            quote = pool.get(rule.slug)
            if quote is None:
                outcome.skipped_missing.append(rule.slug)
                continue
            if not quote.is_usable:
                # دادهٔ کهنه هرگز هشدار «الان» نمی‌سازد
                outcome.skipped_stale.append(rule.slug)
                self.storage.alerts.mark_checked(rule.id, quote.price)
                continue

            if not self.matches(rule, quote):
                self.storage.alerts.mark_checked(rule.id, quote.price)
                continue

            message = self.describe(rule, quote)
            cooldown_left = self._cooldown_left(rule, now)
            if cooldown_left > 0:
                outcome.suppressed.append(
                    self.storage.alerts.log_event(
                        slug=rule.slug, kind=rule.kind.value, price=quote.price,
                        threshold=rule.threshold, message=message, rule_id=rule.id,
                        owner=rule.owner, suppressed=True,
                        reason=f"در بازهٔ خنک‌شدن ({fa_number(int(cooldown_left))} ثانیه باقی‌مانده)",
                        at=now,
                    )
                )
                self.storage.alerts.mark_checked(rule.id, quote.price)
                continue

            owner_key = rule.owner or "-"
            if owner_counts.get(owner_key, 0) >= RATE_MAX_EVENTS:
                outcome.suppressed.append(
                    self.storage.alerts.log_event(
                        slug=rule.slug, kind=rule.kind.value, price=quote.price,
                        threshold=rule.threshold, message=message, rule_id=rule.id,
                        owner=rule.owner, suppressed=True,
                        reason="سقف نرخ آگاه‌سازی در این بازه",
                        at=now,
                    )
                )
                self.storage.alerts.mark_checked(rule.id, quote.price)
                continue

            stored = self.storage.alerts.log_event(
                slug=rule.slug, kind=rule.kind.value, price=quote.price,
                threshold=rule.threshold, message=message, rule_id=rule.id,
                owner=rule.owner, at=now,
            )
            self.storage.alerts.mark_fired(rule.id, quote.price, now)
            owner_counts[owner_key] = owner_counts.get(owner_key, 0) + 1
            outcome.fired.append(stored)

            if rule.one_shot:
                self.storage.alerts.set_status(rule.id, AlertStatus.PAUSED)

        if outcome.fired or outcome.suppressed:
            self.storage.alerts.prune_events(self.config.alerts.max_events)
        log.info(
            "alert evaluation: %d checked, %d notified, %d suppressed",
            outcome.checked, len(outcome.fired), len(outcome.suppressed),
        )
        return outcome

    # --------------------------------------------------------------- helpers
    @staticmethod
    def matches(rule: AlertRule, quote: Quote) -> bool:
        """آیا شرط قاعده برقرار است؟"""
        if rule.kind is AlertKind.ABOVE:
            return quote.price >= rule.threshold
        if rule.kind is AlertKind.BELOW:
            return quote.price <= rule.threshold
        if rule.kind is AlertKind.PCT_MOVE:
            return quote.change_pct is not None and abs(quote.change_pct) >= rule.threshold
        return False

    @staticmethod
    def distance(rule: AlertRule, quote: Quote) -> float | None:
        """فاصلهٔ نسبی قیمت تا آستانه (درصد) — برای نمایش «چقدر مانده»."""
        if rule.kind is AlertKind.PCT_MOVE:
            if quote.change_pct is None:
                return None
            return abs(quote.change_pct) - rule.threshold
        if not quote.price:
            return None
        return (quote.price - rule.threshold) / rule.threshold * 100.0

    def describe(self, rule: AlertRule, quote: Quote) -> str:
        """متن فارسی رخداد — بدون عدد خام لاتین."""
        asset = ASSETS.get(rule.slug)
        title = asset.title if asset else rule.slug
        unit = quote.unit
        precision = asset.precision if asset else 0
        if rule.kind is AlertKind.ABOVE:
            return (
                f"{title} به {fa_price(quote.price, unit, precision)} رسید و از آستانهٔ "
                f"{fa_price(rule.threshold, unit, precision)} گذشت"
            )
        if rule.kind is AlertKind.BELOW:
            return (
                f"{title} به {fa_price(quote.price, unit, precision)} رسید و زیر آستانهٔ "
                f"{fa_price(rule.threshold, unit, precision)} افتاد"
            )
        return (
            f"{title} در ۲۴ ساعت گذشته {fa_percent(quote.change_pct)} تغییر کرد "
            f"(آستانه: {fa_percent(rule.threshold)}) — قیمت فعلی "
            f"{fa_price(quote.price, unit, precision)}"
        )

    def _cooldown_left(self, rule: AlertRule, now: float) -> float:
        """ثانیهٔ باقی‌مانده تا اجازهٔ آگاه‌سازی بعدی.

        ``cooldown_seconds = 0`` یک مقدار معتبر است و یعنی «هر دور آگاه کن»؛
        نباید به پیش‌فرض پیکربندی برگردد. اگر مقدار تعیین نشده باشد (``None``)
        همان پیش‌فرض پیکربندی استفاده می‌شود.
        """
        cooldown = (
            rule.cooldown_seconds
            if rule.cooldown_seconds is not None
            else self.config.alerts.cooldown_seconds
        )
        if cooldown <= 0:
            return 0.0
        last = rule.last_fired_at
        if last is None:
            previous = self.storage.alerts.last_event_for(rule.id)
            last = previous.created_at if previous and not previous.suppressed else None
        if last is None:
            return 0.0
        return max(0.0, cooldown - (now - last))

    # ------------------------------------------------------------------ views
    def rules_view(
        self, *, owner: str | None = None, slug: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> dict:
        """قواعد به‌همراه فاصله تا آستانه — چیزی که کاربر واقعاً می‌خواهد بداند."""
        quotes = self.market.quotes()
        rules = self.storage.alerts.list(owner=owner, slug=slug, limit=limit, offset=offset)
        items = []
        for rule in rules:
            quote = quotes.get(rule.slug)
            entry = rule.to_dict()
            asset = ASSETS.get(rule.slug)
            entry["title"] = asset.title if asset else rule.slug
            entry["symbol"] = asset.symbol if asset else ""
            entry["unit"] = quote.unit if quote else (asset.unit if asset else "toman")
            entry["unit_label"] = "دلار" if entry["unit"] == "usd" else "تومان"
            entry["current_price"] = quote.price if quote else None
            entry["current_price_text"] = (
                fa_price(quote.price, quote.unit, asset.precision if asset else 0) if quote else "—"
            )
            entry["current_pct"] = quote.change_pct if quote else None
            entry["current_pct_text"] = fa_percent(quote.change_pct) if quote else "—"
            entry["direction"] = quote.direction if quote else 0
            entry["freshness"] = quote.freshness.value if quote else "unknown"
            entry["freshness_label"] = quote.freshness.label if quote else "نامعلوم"
            entry["is_usable"] = bool(quote and quote.is_usable)
            distance = self.distance(rule, quote) if quote else None
            entry["distance_pct"] = round(distance, 2) if distance is not None else None
            entry["distance_text"] = fa_percent(distance) if distance is not None else "—"
            entry["threshold_text"] = (
                fa_percent(rule.threshold) if rule.kind is AlertKind.PCT_MOVE
                else fa_number(rule.threshold, asset.precision if asset else 0)
            )
            items.append(entry)
        return {
            "items": items,
            "count": len(items),
            "total": self.storage.alerts.count(owner=owner),
            "stats": self.storage.alerts.stats(),
            "owner": owner,
        }

    def events_view(self, *, owner: str | None = None, slug: str | None = None,
                    include_suppressed: bool = True, limit: int = 50, offset: int = 0) -> dict:
        """دفتر رخداد با متادیتای نمایش."""
        events = self.storage.alerts.events(
            owner=owner, slug=slug, include_suppressed=include_suppressed,
            limit=limit, offset=offset,
        )
        items = []
        for event in events:
            asset = ASSETS.get(event.slug)
            entry = event.to_dict()
            entry["title"] = asset.title if asset else event.slug
            entry["price_text"] = fa_price(event.price, asset.unit if asset else "toman",
                                           asset.precision if asset else 0)
            items.append(entry)
        return {
            "items": items,
            "count": len(items),
            "stats": self.storage.alerts.stats(),
        }

    def preview(self, kind: AlertKind, slug: str, threshold: float) -> dict:
        """پیش‌نمایش: اگر همین حالا این قاعده ساخته شود، الان فعال می‌شود؟"""
        asset = get(slug)
        quote = self.market.quotes().get(slug)
        if quote is None:
            return {"would_fire": False, "reason": "قیمتی برای این دارایی ثبت نشده است"}
        if not quote.is_usable:
            return {"would_fire": False, "reason": "قیمت موجود تازه نیست"}
        rule = AlertRule(
            id=0, slug=slug, kind=kind, threshold=float(threshold), owner="",
            cooldown_seconds=self.config.alerts.cooldown_seconds,
        )
        return {
            "would_fire": self.matches(rule, quote),
            "current_price_text": fa_price(quote.price, quote.unit, asset.precision),
            "current_pct_text": fa_percent(quote.change_pct),
            "distance_text": (
                fa_percent(self.distance(rule, quote)) if self.distance(rule, quote) is not None else "—"
            ),
        }


__all__ = ["AlertEngine", "EvaluationOutcome"]
