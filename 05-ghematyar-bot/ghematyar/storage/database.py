# -*- coding: utf-8 -*-
"""پایگاه دادهٔ SQLite — اتصال، اسکیما و مهاجرت نسخه‌دار.

چند نکتهٔ عملی:

* **WAL** روشن است تا حلقهٔ پایش و هندلرهای ربات هم‌زمان بنویسند و
  قفل‌شدن («database is locked») پیش نیاید.
* هر عملیات در تراکنش کوتاه انجام می‌شود؛ اتصال‌ها کوتاه‌عمر و
  thread-local هستند، چون ربات و پایشگر در حلقه‌های رویداد مجزا کار می‌کنند.
* نسخهٔ اسکیما با ``PRAGMA user_version`` نگه داشته می‌شود و مهاجرت‌ها به
  ترتیب اجرا می‌شوند، پس ارتقای نسخه دادهٔ موجود را از دست نمی‌دهد.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

log = logging.getLogger("ghematyar.storage")

SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        # ---------------------------------------------------------- هشدارها
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL,
            slug              TEXT    NOT NULL,
            direction         TEXT    NOT NULL CHECK (direction IN ('above', 'below')),
            target            REAL    NOT NULL,
            status            TEXT    NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'paused', 'triggered', 'disabled')),
            one_shot          INTEGER NOT NULL DEFAULT 1,
            cooldown_seconds  INTEGER NOT NULL DEFAULT 0,
            last_notified_at  REAL,
            triggered_count   INTEGER NOT NULL DEFAULT 0,
            failure_count     INTEGER NOT NULL DEFAULT 0,
            last_price        REAL,
            last_checked_at   REAL,
            created_at        REAL    NOT NULL,
            updated_at        REAL    NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(slug, status)",
        # جلوگیری از هشدار تکراری دقیقاً یکسان برای یک کاربر
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_alerts_signature
            ON alerts(user_id, slug, direction, target)
            WHERE status IN ('active', 'paused', 'triggered')
        """,
        # ---------------------------------------------------------- رویدادها
        """
        CREATE TABLE IF NOT EXISTS alert_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id    INTEGER,
            user_id     INTEGER NOT NULL,
            slug        TEXT    NOT NULL,
            kind        TEXT    NOT NULL,      -- triggered | suppressed | error | created | updated
            price       REAL,
            target      REAL,
            detail      TEXT    NOT NULL DEFAULT '',
            created_at  REAL    NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_events_user_time ON alert_events(user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_events_alert ON alert_events(alert_id, created_at)",
        # --------------------------------------------------------- تاریخچهٔ قیمت
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slug        TEXT    NOT NULL,
            price       REAL    NOT NULL,
            unit        TEXT    NOT NULL DEFAULT 'toman',
            source      TEXT    NOT NULL DEFAULT '',
            observed_at REAL    NOT NULL,
            captured_at REAL    NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_history_slug_time ON price_history(slug, captured_at)",
        # ------------------------------------------------------------- دیده‌بان
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id     INTEGER NOT NULL,
            slug        TEXT    NOT NULL,
            created_at  REAL    NOT NULL,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, slug)
        )
        """,
        # ------------------------------------------------------------ کاربران
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id         INTEGER PRIMARY KEY,
            chat_id         INTEGER,
            created_at      REAL NOT NULL,
            last_seen_at    REAL NOT NULL,
            notify_enabled  INTEGER NOT NULL DEFAULT 1,
            alerts_muted    INTEGER NOT NULL DEFAULT 0
        )
        """,
    ),
}


class Database:
    """مدیر اتصال و اسکیما.

    اتصال در هر thread نگه داشته می‌شود (`threading.local`) چون aiogram و
    حلقهٔ پایش می‌توانند روی threadهای متفاوت کار کنند.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._local = threading.local()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- connection
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        """اتصال thread-local."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """تراکنش کوتاه با commit/rollback."""
        conn = self.connection
        conn.execute("BEGIN")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    def close(self) -> None:
        """بستن اتصال همین thread."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ---------------------------------------------------------------- schema
    def migrate(self) -> int:
        """اجرای مهاجرت‌های عقب‌مانده و برگرداندن نسخهٔ نهایی."""
        conn = self.connection
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        for version in sorted(_MIGRATIONS):
            if version <= current:
                continue
            for statement in _MIGRATIONS[version]:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")
            current = version
            log.info("applied schema migration %d", version)
        return current

    # ------------------------------------------------------------- utilities
    def is_empty(self) -> bool:
        """آیا هیچ هشداری ثبت نشده است؟"""
        row = self.connection.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()
        return int(row["n"]) == 0
