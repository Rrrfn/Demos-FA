# -*- coding: utf-8 -*-
"""ریپازیتوری دیده‌بان.

دیده‌بان فقط برای مهمان‌هاست: بدون حساب کاربری هم کار می‌کند، چون در نمای
عمومی هر بازدیدکننده یک شناسهٔ نشستی دارد. کلید اصلی مرکب ``(مالک، دارایی)``
از ثبت تکراری جلوگیری می‌کند.
"""
from __future__ import annotations

import time

from ..assets import exists


class WatchlistRepository:
    """اقلام دیده‌شدهٔ هر مالک."""

    def __init__(self, storage) -> None:  # noqa: ANN001 - Storage
        self.storage = storage

    def add(self, owner: str, slug: str) -> bool:
        """افزودن قلم؛ اگر از قبل بود ``False`` برمی‌گرداند."""
        if not exists(slug):
            return False
        with self.storage.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO watchlist (owner, slug, created_at) VALUES (?,?,?) "
                "ON CONFLICT(owner, slug) DO NOTHING",
                (owner, slug, time.time()),
            )
            return bool(cursor.rowcount)

    def remove(self, owner: str, slug: str) -> bool:
        """حذف قلم؛ اگر وجود نداشت ``False``."""
        with self.storage.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM watchlist WHERE owner = ? AND slug = ?", (owner, slug)
            )
            return bool(cursor.rowcount)

    def toggle(self, owner: str, slug: str) -> bool:
        """جابه‌جایی وضعیت؛ خروجی یعنی «الان در دیده‌بان است»."""
        if self.has(owner, slug):
            self.remove(owner, slug)
            return False
        return self.add(owner, slug)

    def has(self, owner: str, slug: str) -> bool:
        row = self.storage.query_one(
            "SELECT 1 AS x FROM watchlist WHERE owner = ? AND slug = ?", (owner, slug)
        )
        return row is not None

    def slugs(self, owner: str) -> list[str]:
        """اقلام دیده‌بان به‌ترتیب افزودن."""
        rows = self.storage.query(
            "SELECT slug FROM watchlist WHERE owner = ? ORDER BY created_at ASC", (owner,)
        )
        return [row["slug"] for row in rows]

    def entries(self, owner: str) -> list[dict]:
        """اقلام همراه با زمان افزودن."""
        rows = self.storage.query(
            "SELECT slug, created_at FROM watchlist WHERE owner = ? ORDER BY created_at ASC",
            (owner,),
        )
        return [{"slug": row["slug"], "created_at": row["created_at"]} for row in rows]

    def clear(self, owner: str) -> int:
        row = self.storage.query_one(
            "SELECT COUNT(*) AS n FROM watchlist WHERE owner = ?", (owner,)
        )
        self.storage.execute("DELETE FROM watchlist WHERE owner = ?", (owner,))
        return int(row["n"]) if row else 0

    def count(self, owner: str) -> int:
        row = self.storage.query_one(
            "SELECT COUNT(*) AS n FROM watchlist WHERE owner = ?", (owner,)
        )
        return int(row["n"]) if row else 0

    def owners(self, slug: str) -> list[str]:
        """چه مالکانی این قلم را دیده‌بان کرده‌اند."""
        rows = self.storage.query(
            "SELECT owner FROM watchlist WHERE slug = ? ORDER BY created_at ASC", (slug,)
        )
        return [row["owner"] for row in rows]


__all__ = ["WatchlistRepository"]
