# -*- coding: utf-8 -*-
"""پایگاه داده — اسکیما، مهاجرت و اتصال.

طراحی داده:

* ``readings`` سری زمانی کامل مشاهدات است (منبع نمودار و محاسبهٔ تغییر).
* ``quotes`` آخرین وضعیت هر دارایی را نگه می‌دارد، به‌همراه قیمت قبلی —
  همین جدول است که «قیمت فعلی / قیمت قبلی / تغییر» را بدون اسکن کل تاریخچه
  در دسترس می‌گذارد.
* ``source_runs`` تاریخچهٔ سلامت منابع را ثبت می‌کند تا داشبورد بتواند
  وضعیت هر منبع را از داده واقعی نشان دهد، نه از حافظهٔ پروسه.

حالت ``WAL`` فعال است تا خواندن‌ها هنگام نوشتن جمع‌آور بلاک نشوند.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("cheshmbaz.storage")

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    slug      TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    kind      TEXT NOT NULL,
    unit      TEXT NOT NULL,
    symbol    TEXT NOT NULL DEFAULT '',
    precision INTEGER NOT NULL DEFAULT 0
);

-- آخرین وضعیت هر دارایی + قیمت قبلی
CREATE TABLE IF NOT EXISTS quotes (
    slug           TEXT PRIMARY KEY,
    price          REAL NOT NULL,
    unit           TEXT NOT NULL,
    source         TEXT NOT NULL,
    observed_at    REAL NOT NULL,
    fetched_at     REAL NOT NULL,
    day_low        REAL,
    day_high       REAL,
    change_abs     REAL,
    change_pct     REAL,
    change_basis   TEXT NOT NULL DEFAULT '',
    previous_price REAL,
    previous_at    REAL,
    updated_at     REAL NOT NULL
);

-- سری زمانی مشاهدات
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL,
    price       REAL NOT NULL,
    unit        TEXT NOT NULL DEFAULT 'toman',
    source      TEXT NOT NULL,
    observed_at REAL NOT NULL,
    fetched_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_readings_slug_observed ON readings(slug, observed_at);

-- سلامت منابع
CREATE TABLE IF NOT EXISTS source_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    ok         INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    items      INTEGER NOT NULL DEFAULT 0,
    error      TEXT NOT NULL DEFAULT '',
    checked_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_source_runs_name_time ON source_runs(name, checked_at);

-- قواعد هشدار
CREATE TABLE IF NOT EXISTS alert_rules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    owner            TEXT NOT NULL DEFAULT '',
    slug             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    threshold        REAL NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',
    one_shot         INTEGER NOT NULL DEFAULT 0,
    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
    note             TEXT NOT NULL DEFAULT '',
    created_at       REAL NOT NULL,
    last_fired_at    REAL,
    last_price       REAL,
    fired_count      INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_rules_identity
    ON alert_rules(owner, slug, kind, threshold);
CREATE INDEX IF NOT EXISTS ix_alert_rules_status ON alert_rules(status, slug);

-- رخدادهای هشدار
CREATE TABLE IF NOT EXISTS alert_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id    INTEGER,
    slug       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    price      REAL NOT NULL,
    threshold  REAL NOT NULL DEFAULT 0,
    message    TEXT NOT NULL,
    created_at REAL NOT NULL,
    suppressed INTEGER NOT NULL DEFAULT 0,
    reason     TEXT NOT NULL DEFAULT '',
    owner      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_alert_events_time ON alert_events(created_at);
CREATE INDEX IF NOT EXISTS ix_alert_events_rule ON alert_events(rule_id, created_at);

-- دیده‌بان
CREATE TABLE IF NOT EXISTS watchlist (
    owner      TEXT NOT NULL,
    slug       TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (owner, slug)
);
"""


class Storage:
    """دسترسی واحد به پایگاه داده و ریپازیتوری‌ها."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        # ریپازیتوری‌ها بعد از ساخت اسکیما ساخته می‌شوند
        from .alerts import AlertRepository
        from .history import HistoryRepository
        from .quotes import QuoteRepository
        from .sources import SourceRepository
        from .watchlist import WatchlistRepository

        self.quotes = QuoteRepository(self)
        self.history = HistoryRepository(self)
        self.alerts = AlertRepository(self)
        self.sources = SourceRepository(self)
        self.watchlist = WatchlistRepository(self)

    # ------------------------------------------------------------- connection
    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 8000")
        return connection

    @contextmanager
    def transaction(self):
        """اتصال تراکنشی: موفقیت = commit، خطا = rollback."""
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        connection = self.connect()
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(sql, params)
            return cursor.lastrowid or cursor.rowcount

    def close(self) -> None:
        """سازگاری با رابط سرویس‌ها؛ اتصال‌ها کوتاه‌عمر هستند."""
        return None

    # ----------------------------------------------------------------- schema
    def _init_schema(self) -> None:
        with self.transaction() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            current = int(row["value"]) if row else 0
            if current < SCHEMA_VERSION:
                connection.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(SCHEMA_VERSION),),
                )
                log.info("schema initialised at version %d", SCHEMA_VERSION)

    def schema_version(self) -> int:
        row = self.query_one("SELECT value FROM meta WHERE key = 'schema_version'")
        return int(row["value"]) if row else 0

    # ------------------------------------------------------------- maintenance
    def stats(self) -> dict:
        """آمار پایگاه داده برای پنل وضعیت."""
        readings = self.query_one("SELECT COUNT(*) AS n FROM readings")
        quotes = self.query_one("SELECT COUNT(*) AS n FROM quotes")
        events = self.query_one("SELECT COUNT(*) AS n FROM alert_events")
        rules = self.query_one("SELECT COUNT(*) AS n FROM alert_rules")
        span = self.query_one("SELECT MIN(observed_at) AS lo, MAX(observed_at) AS hi FROM readings")
        size = self.path.stat().st_size if self.path.exists() else 0
        return {
            "schema_version": self.schema_version(),
            "readings": readings["n"] if readings else 0,
            "quotes": quotes["n"] if quotes else 0,
            "alert_rules": rules["n"] if rules else 0,
            "alert_events": events["n"] if events else 0,
            "oldest_reading": span["lo"] if span else None,
            "newest_reading": span["hi"] if span else None,
            "size_bytes": size,
            "path": str(self.path),
        }

    def sync_assets(self, assets) -> None:
        """آینه‌کردن رجیستری دارایی‌ها در پایگاه داده."""
        with self.transaction() as connection:
            connection.executemany(
                "INSERT INTO assets (slug, title, kind, unit, symbol, precision) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET "
                "title = excluded.title, kind = excluded.kind, unit = excluded.unit, "
                "symbol = excluded.symbol, precision = excluded.precision",
                [
                    (a.slug, a.title, a.kind.value, a.unit, a.symbol, a.precision)
                    for a in assets
                ],
            )

    def prune(self, retention_days: int) -> dict:
        """پیرایش دادهٔ قدیمی — بدون دست‌زدن به آخرین وضعیت اقلام."""
        cutoff = time.time() - retention_days * 86400
        with self.transaction() as connection:
            readings = connection.execute(
                "DELETE FROM readings WHERE observed_at < ?", (cutoff,)
            ).rowcount
            runs = connection.execute(
                "DELETE FROM source_runs WHERE checked_at < ?", (cutoff,)
            ).rowcount
        return {"readings": max(0, readings), "source_runs": max(0, runs)}


def open_storage(path: str | Path) -> Storage:
    return Storage(path)


__all__ = ["SCHEMA", "SCHEMA_VERSION", "Storage", "open_storage"]
