# -*- coding: utf-8 -*-
"""لایهٔ ذخیره‌سازی — SQLite و انبارهای داده."""
from __future__ import annotations

from pathlib import Path

from .alerts import (
    Alert,
    AlertDirection,
    AlertEventRepository,
    AlertRepository,
    AlertStatus,
)
from .database import SCHEMA_VERSION, Database
from .history import HistoryRepository
from .watchlist import UserRepository, WatchlistRepository

__all__ = [
    "Alert",
    "AlertDirection",
    "AlertEventRepository",
    "AlertRepository",
    "AlertStatus",
    "Database",
    "HistoryRepository",
    "SCHEMA_VERSION",
    "UserRepository",
    "WatchlistRepository",
    "Storage",
    "open_storage",
]


class Storage:
    """دسترسی یک‌جا به همهٔ انبارها روی یک پایگاه داده."""

    def __init__(self, path: str | Path) -> None:
        self.database = Database(path)
        self.database.migrate()
        self.alerts = AlertRepository(self.database)
        self.events = AlertEventRepository(self.database)
        self.history = HistoryRepository(self.database)
        self.watchlist = WatchlistRepository(self.database)
        self.users = UserRepository(self.database)

    @property
    def path(self) -> Path:
        return self.database.path

    def close(self) -> None:
        self.database.close()


def open_storage(path: str | Path) -> Storage:
    """باز کردن (و در صورت نیاز ساختن) پایگاه داده با اسکیمای کامل."""
    return Storage(path)
