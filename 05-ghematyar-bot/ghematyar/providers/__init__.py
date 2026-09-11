# -*- coding: utf-8 -*-
"""لایهٔ ارائه‌دهندهٔ داده — هر منبع جدا، با مدارشکن و خطای صریح.

مرتبهٔ fallback بر پایهٔ اندازه‌گیری واقعی انتخاب شده است:

* **بازار داخل (طلا، سکه، ارز)** → tgju. تنها منبع قابل‌اتکای در دسترس است
  (Nobitex از این شبکه پاسخ نمی‌دهد). دو میزبان خوراک و یک مسیر HTML
  به‌عنوان fallback همان خانواده به‌کار می‌رود.
* **رمزارز** → CoinGecko اوّل، tgju دوم. این دو منبع مستقل‌اند، پس fallback
  واقعی است و حتی امکان مقایسهٔ متقاطع می‌دهد.
"""
from .base import BaseProvider, CircuitBreaker, HttpClient, MarketProvider
from .coingecko import CoinGeckoProvider
from .tgju import TgjuProvider

__all__ = [
    "BaseProvider",
    "CircuitBreaker",
    "CoinGeckoProvider",
    "HttpClient",
    "MarketProvider",
    "TgjuProvider",
]
