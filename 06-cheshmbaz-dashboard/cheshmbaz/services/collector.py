# -*- coding: utf-8 -*-
"""جمع‌آور — پلی بین منابع داده، سرویس قیمت و ذخیره‌سازی.

مسئولیت‌ها:

* واکشی هر منبع به‌صورت مستقل؛ شکست یک منبع بقیه را متوقف نمی‌کند.
* **محاسبهٔ تغییر از تاریخچهٔ خودمان** برای اقلامی که منبعشان درصد تغییر
  نمی‌دهد (طلا، سکه و ارز). هیچ جایی عدد تغییر ساخته نمی‌شود: نبود مرجع یعنی
  درصد «—» می‌ماند.
* ثبت سلامت هر منبع، چه موفق چه ناموفق.
* جلوگیری از اجرای هم‌زمان در چند پروسه با «قرارداد جمع‌آوری» — اجرای موازی
  دو نمونه، تاریخچه را با نمونه‌های تکراری آلوده می‌کند.

ترتیب کار مهم است: مرجع تغییر **پیش از** ثبت مشاهدهٔ تازه خوانده می‌شود تا
مشاهدهٔ جدید مرجع خودش نشود.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from ..assets import all_assets_ordered, by_provider
from ..config import Config
from ..core.models import Quote, SourceStatus, clone_quote
from ..providers import build_providers
from ..providers.base import BaseProvider, HttpClient
from ..storage import Storage

log = logging.getLogger("cheshmbaz.collector")

#: بازهٔ مرجع برای درصد تغییر اقلام داخلی — ۲۴ ساعت
CHANGE_WINDOW_SECONDS = 86_400
LEASE_KEY = "collector_lease"


@dataclass(slots=True)
class ProviderRun:
    """نتیجهٔ یک بار واکشی از یک منبع."""

    name: str
    ok: bool
    requested: int = 0
    received: int = 0
    missing: list[str] = field(default_factory=list)
    latency_ms: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "requested": self.requested,
            "received": self.received,
            "missing": self.missing,
            "latency_ms": self.latency_ms,
            "error": self.error or None,
        }


@dataclass(slots=True)
class CollectionResult:
    """حاصل یک دور کامل جمع‌آوری."""

    started_at: float
    finished_at: float = 0.0
    providers: list[ProviderRun] = field(default_factory=list)
    quotes_received: int = 0
    quotes_saved: int = 0
    readings_saved: int = 0
    with_change: int = 0
    skipped: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return any(run.ok and run.received for run in self.providers)

    @property
    def duration_ms(self) -> int:
        return int((self.finished_at - self.started_at) * 1000) if self.finished_at else 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "skipped": self.skipped,
            "reason": self.reason or None,
            "started_at": self.started_at,
            "finished_at": self.finished_at or None,
            "duration_ms": self.duration_ms,
            "quotes_received": self.quotes_received,
            "quotes_saved": self.quotes_saved,
            "readings_saved": self.readings_saved,
            "with_change": self.with_change,
            "providers": [run.to_dict() for run in self.providers],
        }


class Collector:
    """واکشی و ثبت قیمت‌های واقعی."""

    def __init__(
        self,
        config: Config,
        storage: Storage,
        *,
        providers: dict[str, BaseProvider] | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.http = http or HttpClient(config.data)
        self.providers = providers if providers is not None else build_providers(self.http, config.data)
        self._lease_owner = f"{os.getpid()}@{int(time.time())}"

    # ------------------------------------------------------------------ lease
    def _lease_seconds(self) -> int:
        """قرارداد به‌اندازهٔ نصف بازهٔ جمع‌آوری معتبر است."""
        return max(60, self.config.collector.interval_seconds // 2)

    def acquire_lease(self) -> bool:
        """گرفتن قرارداد جمع‌آوری — در تعدد پروسه از تکرار جلوگیری می‌کند."""
        now = time.time()
        with self.storage.transaction() as connection:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = ?", (LEASE_KEY,)
            ).fetchone()
            if row and row["value"]:
                owner, _, expires = row["value"].partition("|")
                try:
                    expires_at = float(expires)
                except ValueError:
                    expires_at = 0.0
                if owner != self._lease_owner and expires_at > now:
                    return False
            connection.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (LEASE_KEY, f"{self._lease_owner}|{now + self._lease_seconds()}"),
            )
        return True

    def release_lease(self) -> None:
        """آزادکردن قرارداد (اجرای دستی نباید بازهٔ بعدی را بلاک کند)."""
        with self.storage.transaction() as connection:
            connection.execute("DELETE FROM meta WHERE key = ?", (LEASE_KEY,))

    def lease_holder(self) -> str | None:
        row = self.storage.query_one("SELECT value FROM meta WHERE key = ?", (LEASE_KEY,))
        return row["value"] if row else None

    # -------------------------------------------------------------- main flow
    def collect(self, *, use_lease: bool = True) -> CollectionResult:
        """یک دور کامل واکشی و ثبت."""
        result = CollectionResult(started_at=time.time())

        if use_lease and not self.acquire_lease():
            result.skipped = True
            result.reason = "دور دیگری از جمع‌آوری در حال اجراست"
            result.finished_at = time.time()
            return result

        try:
            fetched: dict[str, Quote] = {}
            for name, provider in self.providers.items():
                run, quotes = self._run_provider(name, provider)
                result.providers.append(run)
                fetched.update(quotes)

            result.quotes_received = len(fetched)

            if fetched:
                self._apply_history_change(fetched)
                result.with_change = sum(1 for q in fetched.values() if q.change_pct is not None)
                for quote in fetched.values():
                    quote.mark_freshness(
                        self.config.data.live_within,
                        self.config.data.stale_after,
                        self.config.data.expire_after,
                    )
                result.readings_saved = self.storage.history.record_many(fetched)
                result.quotes_saved = self.storage.quotes.save_many(fetched)
        finally:
            result.finished_at = time.time()
            if use_lease:
                self.release_lease()

        log.info(
            "collection finished in %dms: %d quotes, %d readings",
            result.duration_ms, result.quotes_saved, result.readings_saved,
        )
        return result

    # ------------------------------------------------------------- internals
    def _run_provider(self, name: str, provider: BaseProvider) -> tuple[ProviderRun, dict[str, Quote]]:
        """واکشی یک منبع با ثبت سلامت — شکست فقط همین منبع را زمین می‌زند."""
        assets = by_provider(name)
        if not assets:
            return ProviderRun(name=name, ok=True, requested=0), {}

        started = time.perf_counter()
        try:
            outcome = provider.fetch(assets)
        except Exception as error:  # noqa: BLE001 - هر شکست باید ثبت شود
            latency = int((time.perf_counter() - started) * 1000)
            message = getattr(error, "raw_message", None) or str(error)
            log.warning("provider %s failed: %s", name, message)
            self.storage.sources.record(
                SourceStatus(
                    name=name, ok=False, latency_ms=latency, items=0,
                    error=message, checked_at=time.time(),
                )
            )
            return (
                ProviderRun(name=name, ok=False, requested=len(assets), latency_ms=latency, error=message),
                {},
            )

        received = list(outcome.quotes)
        missing = [asset.slug for asset in assets if asset.slug not in outcome.quotes]
        self.storage.sources.record(
            SourceStatus(
                name=name, ok=True, latency_ms=outcome.latency_ms or int((time.perf_counter() - started) * 1000),
                items=len(received), error="", checked_at=time.time(),
            )
        )
        return (
            ProviderRun(
                name=name, ok=True, requested=len(assets), received=len(received),
                missing=missing, latency_ms=outcome.latency_ms, error="",
            ),
            dict(outcome.quotes),
        )

    def _apply_history_change(self, quotes: dict[str, Quote]) -> None:
        """محاسبهٔ تغییر ۲۴ ساعته از تاریخچهٔ ثبت‌شدهٔ خودمان.

        فقط برای اقلامی که منبعشان تغییر نمی‌دهد. اگر مرجع تاریخی وجود
        نداشته باشد، هیچ عددی ساخته نمی‌شود و درصد خالی می‌ماند.
        """
        for slug, quote in quotes.items():
            if quote.change_pct is not None:
                continue
            reference = self.storage.history.reference(slug, seconds=CHANGE_WINDOW_SECONDS)
            if reference is None:
                continue
            previous_price, previous_at = reference
            if previous_price <= 0 or quote.price <= 0:
                continue
            change = quote.price - previous_price
            if abs(change) < 1e-9:
                change = 0.0
            quote.previous_price = previous_price
            quote.previous_at = previous_at
            quote.change_abs = change
            quote.change_pct = (change / previous_price) * 100.0
            quote.change_basis = "۲۴ ساعته (تاریخچهٔ ثبت‌شده)"

    # ------------------------------------------------------------ inspection
    def provider_health(self) -> list[dict]:
        """وضعیت ترکیبی منابع: آخرین اجرا + مدارشکن."""
        breakers = {item["name"]: item for item in self.http.breaker_states()}
        latest = {status.name: status for status in self.storage.sources.latest()}
        out = []
        for name in self.providers:
            stored = latest.get(name)
            entry = {
                "name": name,
                "last_ok": stored.ok if stored else None,
                "last_checked_at": stored.checked_at if stored else None,
                "last_latency_ms": stored.latency_ms if stored else None,
                "last_error": (stored.error or None) if stored else None,
                "reliability": self.storage.sources.reliability(name),
                "breaker": breakers.get(name),
            }
            out.append(entry)
        return out


def seed_registry(storage: Storage) -> None:
    """آینه‌کردن رجیستری دارایی‌ها در پایگاه داده (بی‌عارضه و تکرارپذیر)."""
    storage.sync_assets(all_assets_ordered())


def clone_all(quotes: dict[str, Quote]) -> dict[str, Quote]:
    """کپی گروهی — تا دست‌کاری تازگی روی نسخهٔ ذخیره‌شده اثر نگذارد."""
    return {slug: clone_quote(quote) for slug, quote in quotes.items()}


__all__ = [
    "CHANGE_WINDOW_SECONDS",
    "CollectionResult",
    "Collector",
    "ProviderRun",
    "clone_all",
    "seed_registry",
]
