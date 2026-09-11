# -*- coding: utf-8 -*-
"""دیده‌بان کاربر و وضعیت کاربران."""
from __future__ import annotations

import time

from .database import Database


class WatchlistRepository:
    """اقلام نشان‌شدهٔ کاربر برای دسترسی سریع و پیام خلاصه."""

    def __init__(self, db: Database, *, limit: int = 12) -> None:
        self.db = db
        self.limit = limit

    def list_for_user(self, user_id: int) -> list[str]:
        rows = self.db.connection.execute(
            "SELECT slug FROM watchlist WHERE user_id = ? ORDER BY sort_order, created_at",
            (user_id,),
        ).fetchall()
        return [str(r["slug"]) for r in rows]

    def contains(self, user_id: int, slug: str) -> bool:
        row = self.db.connection.execute(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND slug = ?", (user_id, slug)
        ).fetchone()
        return row is not None

    def count(self, user_id: int) -> int:
        row = self.db.connection.execute(
            "SELECT COUNT(*) AS n FROM watchlist WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row["n"])

    def add(self, user_id: int, slug: str) -> bool:
        """افزودن قلم. اگر به سقف رسیده یا تکراری باشد ``False``."""
        with self.db.transaction() as conn:
            if self.contains(user_id, slug):
                return False
            if self.count(user_id) >= self.limit:
                return False
            conn.execute(
                "INSERT INTO watchlist (user_id, slug, created_at, sort_order) VALUES (?,?,?,?)",
                (user_id, slug, time.time(), self.count(user_id)),
            )
            return True

    def remove(self, user_id: int, slug: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND slug = ?", (user_id, slug)
            )
            return cursor.rowcount > 0

    def toggle(self, user_id: int, slug: str) -> bool:
        """تغییر وضعیت. برمی‌گرداند آیا پس از عملیات در فهرست هست."""
        if self.contains(user_id, slug):
            self.remove(user_id, slug)
            return False
        return self.add(user_id, slug)

    def clear(self, user_id: int) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))
            return cursor.rowcount


class UserRepository:
    """ثبت کاربر و ترجیحات اعلان."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def touch(self, user_id: int, chat_id: int | None = None) -> None:
        """ثبت/به‌روزرسانی کاربر در هر تعامل."""
        now = time.time()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO users (user_id, chat_id, created_at, last_seen_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE
                   SET last_seen_at = excluded.last_seen_at,
                       chat_id = COALESCE(excluded.chat_id, users.chat_id)""",
                (user_id, chat_id, now, now),
            )

    def get(self, user_id: int) -> dict | None:
        row = self.db.connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def set_notifications(self, user_id: int, enabled: bool) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE users SET notify_enabled = ? WHERE user_id = ?",
                (int(enabled), user_id),
            )

    def notifications_enabled(self, user_id: int) -> bool:
        """پیش‌فرض: اعلان روشن است، حتی اگر کاربر ثبت نشده باشد."""
        state = self.get(user_id)
        if state is None:
            return True
        return bool(state["notify_enabled"])

    def count(self) -> int:
        row = self.db.connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"])
