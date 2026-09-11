# -*- coding: utf-8 -*-
"""منبع رمزارز (CoinGecko) — منبعی مستقل از بازار داخلی.

چرا مستقل: اگر رمزارزها هم از همان منبع بازار داخلی خوانده شوند، قطعی یک
منبع کل داشبورد را از کار می‌اندازد. علاوه بر آن، این منبع دو چیزی می‌دهد
که خوراک داخلی ندارد:

* **درصد تغییر ۲۴ ساعتهٔ واقعی** (``include_24hr_change``)
* **زمان مشاهدهٔ منتشرشدهٔ خود منبع** (``include_last_updated_at``)

نکتهٔ محاسبه: تغییر ۲۴ ساعته نسبت به قیمت ۲۴ ساعت پیش است، پس قیمت قبلی از
رابطهٔ ``previous = price / (1 + pct/100)`` به دست می‌آید، نه با تفریق ساده.
"""
from __future__ import annotations

import time
from typing import Any, Sequence

from ..core.models import Asset, Quote
from .base import BaseProvider, HttpClient, ProviderResult

API_URL = "https://api.coingecko.com/api/v3/simple/price"
#: سقف شناسه در هر درخواست تا طول نشانی معقول بماند
MAX_IDS_PER_REQUEST = 40
CURRENCY = "usd"


def build_url(ids: Sequence[str]) -> str:
    """ساخت نشانی درخواست."""
    joined = ",".join(ids)
    return (
        f"{API_URL}?ids={joined}&vs_currencies={CURRENCY}"
        "&include_24hr_change=true&include_last_updated_at=true"
    )


def parse_quotes(
    payload: Any, assets: Sequence[Asset], *, fetched_at: float | None = None
) -> tuple[dict[str, Quote], list[str]]:
    """پارس خالص پاسخ — بدون شبکه، برای تست مستقیم."""
    stamp = fetched_at if fetched_at is not None else time.time()
    if not isinstance(payload, dict):
        return {}, [asset.slug for asset in assets]

    quotes: dict[str, Quote] = {}
    missing: list[str] = []

    for asset in assets:
        record = payload.get(asset.provider_key or asset.slug)
        if not isinstance(record, dict):
            missing.append(asset.slug)
            continue

        price = record.get(CURRENCY)
        if not isinstance(price, (int, float)) or price <= 0:
            missing.append(asset.slug)
            continue

        pct = record.get(f"{CURRENCY}_24h_change")
        pct = float(pct) if isinstance(pct, (int, float)) else None
        source_stamp = record.get("last_updated_at")
        observed = float(source_stamp) if isinstance(source_stamp, (int, float)) else stamp

        previous = None
        change_abs = None
        basis = ""
        if pct is not None and pct != -100:
            previous = price / (1 + pct / 100.0)
            change_abs = price - previous
            basis = "۲۴ ساعتهٔ منبع"

        quotes[asset.slug] = Quote(
            slug=asset.slug,
            price=float(price),
            unit=CURRENCY,
            source="coingecko.com",
            observed_at=observed,
            fetched_at=stamp,
            change_abs=change_abs,
            change_pct=pct,
            change_basis=basis,
            precision=asset.precision,
            previous_price=previous,
            previous_at=observed - 86400 if previous is not None else None,
        )

    return quotes, missing


class CoinGeckoProvider(BaseProvider):
    """ارائه‌دهندهٔ رمزارز."""

    name = "coingecko"

    def fetch(self, assets: Sequence[Asset]) -> ProviderResult:
        started = time.perf_counter()
        crypto = [asset for asset in assets if asset.is_crypto]
        if not crypto:
            return ProviderResult(name=self.name, requested=0)

        quotes: dict[str, Quote] = {}
        last_error: Exception | None = None

        for start in range(0, len(crypto), MAX_IDS_PER_REQUEST):
            chunk = crypto[start : start + MAX_IDS_PER_REQUEST]
            ids = [asset.provider_key or asset.slug for asset in chunk]
            try:
                payload = self.http.get_json(build_url(ids), provider=self.name)
            except Exception as error:  # noqa: BLE001 - شبکه، مهلت یا JSON
                last_error = error
                continue
            found, _ = parse_quotes(payload, chunk)
            quotes.update(found)

        if not quotes and last_error is not None:
            raise last_error

        self.mark_stale(quotes)
        latency = int((time.perf_counter() - started) * 1000)
        return ProviderResult(
            name=self.name, quotes=quotes, latency_ms=latency, requested=len(crypto)
        )


__all__ = ["API_URL", "CoinGeckoProvider", "build_url", "parse_quotes"]
