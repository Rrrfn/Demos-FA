# -*- coding: utf-8 -*-
"""لایهٔ ذخیره‌سازی — پایگاه داده و ریپازیتوری‌ها."""
from __future__ import annotations

from .alerts import AlertRepository
from .database import SCHEMA_VERSION, Storage, open_storage
from .history import RANGES, HistoryRepository, resolve_range
from .quotes import QuoteRepository
from .sources import SourceRepository
from .watchlist import WatchlistRepository

__all__ = [
    "RANGES",
    "SCHEMA_VERSION",
    "AlertRepository",
    "HistoryRepository",
    "QuoteRepository",
    "SourceRepository",
    "Storage",
    "WatchlistRepository",
    "open_storage",
    "resolve_range",
]
