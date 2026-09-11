# -*- coding: utf-8 -*-
"""لایهٔ منابع داده."""
from __future__ import annotations

from ..config import DataConfig
from .base import BaseProvider, CircuitBreaker, HttpClient, HttpResponse, ProviderResult
from .coingecko import CoinGeckoProvider
from .tgju import TgjuProvider


def build_providers(http: HttpClient, config: DataConfig) -> dict[str, BaseProvider]:
    """منابع پیش‌فرض: بازار داخلی و رمزارز از دو منبع مستقل."""
    providers: list[BaseProvider] = [TgjuProvider(http, config), CoinGeckoProvider(http, config)]
    return {provider.name: provider for provider in providers}


__all__ = [
    "BaseProvider",
    "CircuitBreaker",
    "CoinGeckoProvider",
    "HttpClient",
    "HttpResponse",
    "ProviderResult",
    "TgjuProvider",
    "build_providers",
]
