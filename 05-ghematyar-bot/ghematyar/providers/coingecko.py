# -*- coding: utf-8 -*-
"""ارائه‌دهندهٔ CoinGecko — مرجع مستقل قیمت رمزارزها به دلار.

چرا این منبع:

* **رایگان و بدون کلید** برای نرخ محدود عمومی (کافی برای این حجم درخواست).
* **یک درخواست برای همهٔ رمزارزها** — با endpoint ``simple/price`` چند شناسه
  را یک‌جا می‌دهد، پس نرخ درخواست مصرف نمی‌شود.
* **تغییر ۲۴ ساعتهٔ واقعی** و مهر زمانی به‌ازای هر قلم.
* مستقل از tgju؛ بنابراین برای رمزارزها یک fallback واقعی و متقاطع داریم
  (نه دو مسیر از یک منبع).

محدودیت: نرخ عمومی حدود چند ده درخواست در دقیقه است. با کش ۶۰ ثانیه‌ای
لایهٔ بالاتر، از این سقف فاصلهٔ زیادی داریم و در صورت دریافت ۴۲۹ به‌صورت
کنترل‌شده عقب می‌کشیم.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from ..config import DataConfig
from ..core import assets as asset_registry
from ..core.errors import MalformedResponse
from ..core.models import Quote
from .base import BaseProvider, HttpClient

log = logging.getLogger("ghematyar.providers.coingecko")

BASE_URL = "https://api.coingecko.com/api/v3/simple/price"

# نگاشت شناسهٔ CoinGecko → slug داخلی
_ID_INDEX: dict[str, str] = {
    a.coingecko: a.slug for a in asset_registry.ALL_ASSETS if a.coingecko
}


def parse_simple_price(payload: Any, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
    """پارس پاسخ ``simple/price`` به نقل‌قول‌ها.

    پاسخ نامعتبر یا ساختار غیرمنتظره خطای صریح می‌دهد؛ مقدار خالی مجاز
    است (یعنی منبع برای این اقلام داده‌ای ندارد).
    """
    if not isinstance(payload, dict):
        raise MalformedResponse("coingecko", "payload is not an object")
    if payload.get("status") and isinstance(payload.get("status"), dict):
        # ساختار پیام خطای CoinGecko
        raise MalformedResponse("coingecko", str(payload.get("status")))

    wanted = set(slugs) if slugs else None
    quotes: dict[str, Quote] = {}
    for coin_id, record in payload.items():
        slug = _ID_INDEX.get(coin_id)
        if slug is None or not isinstance(record, dict):
            continue
        if wanted is not None and slug not in wanted:
            continue
        price = record.get("usd")
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        asset = asset_registry.ASSETS[slug]
        updated = record.get("last_updated_at")
        quote = Quote(
            slug=slug,
            price=float(price),
            unit="usd",
            source="coingecko",
            observed_at=float(updated) if isinstance(updated, (int, float)) else None,
            decimals=asset.precision,
        )
        change_pct = record.get("usd_24h_change")
        if isinstance(change_pct, (int, float)):
            quote.change_pct = float(change_pct)
            quote.change_abs = float(price) * float(change_pct) / 100.0
            quote.change_basis = "تغییر ۲۴ ساعته (منبع)"
        quotes[slug] = quote
    return quotes


class CoinGeckoProvider(BaseProvider):
    """ارائه‌دهندهٔ رمزارزها."""

    name = "coingecko"

    def __init__(self, client: HttpClient, config: DataConfig) -> None:
        super().__init__(client, config)

    async def _fetch(self, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
        wanted = [
            s for s in (slugs or asset_registry.ASSETS)
            if asset_registry.exists(s) and asset_registry.ASSETS[s].coingecko
        ]
        if not wanted:
            return {}
        ids = [asset_registry.ASSETS[s].coingecko for s in wanted]
        url = (
            f"{BASE_URL}?ids={','.join(sorted(set(ids)))}"
            "&vs_currencies=usd&include_24hr_change=true&include_last_updated_at=true"
        )
        payload = await self.client.fetch(url, provider="coingecko")
        quotes = parse_simple_price(payload, wanted)
        if not quotes:
            self.last_error = "no rows in payload"
            log.warning("coingecko returned no usable rows")
        return quotes
