# -*- coding: utf-8 -*-
"""تاریخچهٔ قیمت — قلب محاسبهٔ «تغییر» و نمودار.

چرا لازم است: خوراک بازار داخل برای طلا/سکه/ارز هیچ درصد تغییری منتشر
نمی‌کند. به‌جای ساختن عدد از هوا، مشاهده‌ها را با مهر زمانی ذخیره می‌کنیم و
تغییر را نسبت به یک نقطهٔ واقعیِ گذشته حساب می‌کنیم.

مدل داده: ``(slug, price, unit, source, observed_at, captured_at)`` — یعنی
هم زمان انتشار نزد منبع و هم زمان ثبت ما. این تفکیک باعث می‌شود بتوانیم
«داده کهنه» را تشخیص بدهیم.
"""
from __future__ import annotations

import sqlite3
import time

from ..core.models import PricePoint, Quote
from .database import Database


class HistoryRepository:
    """ثبت و خواندن مشاهده‌های قیمت."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ write
    def record(self, quote: Quote) -> None:
        """ثبت یک مشاهده."""
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO price_history
                       (slug, price, unit, source, observed_at, captured_at)
                   VALUES (?,?,?,?,?,?)""",
                (quote.slug, float(quote.price), quote.unit, quote.source,
                 float(quote.observed_at), float(quote.fetched_at)),
            )

    def record_many(self, quotes: dict[str, Quote], *, min_gap_seconds: int = 60) -> int:
        """ثبت گروهی، با نمونه‌برداری حداقلی برای جلوگیری از انبوه رکورد.

        اگر آخرین مشاهدهٔ یک قلم کمتر از ``min_gap_seconds`` پیش ثبت شده
        باشد، دوباره ذخیره نمی‌شود؛ در غیر این صورت هر به‌روزرسانی کش یک
        رکورد اضافه می‌کرد.
        """
        now = time.time()
        written = 0
        with self.db.transaction() as conn:
            for slug, quote in quotes.items():
                row = conn.execute(
                    "SELECT captured_at FROM price_history WHERE slug = ? "
                    "ORDER BY captured_at DESC LIMIT 1",
                    (slug,),
                ).fetchone()
                if row and now - float(row["captured_at"]) < min_gap_seconds:
                    continue
                conn.execute(
                    """INSERT INTO price_history
                           (slug, price, unit, source, observed_at, captured_at)
                       VALUES (?,?,?,?,?,?)""",
                    (slug, float(quote.price), quote.unit, quote.source,
                     float(quote.observed_at), float(quote.fetched_at)),
                )
                written += 1
        return written

    # ------------------------------------------------------------------- read
    def latest(self, slug: str) -> PricePoint | None:
        """آخرین مشاهدهٔ ثبت‌شده."""
        row = self.db.connection.execute(
            "SELECT * FROM price_history WHERE slug = ? ORDER BY captured_at DESC LIMIT 1",
            (slug,),
        ).fetchone()
        return _to_point(row) if row else None

    def price_at_or_before(self, slug: str, timestamp: float) -> PricePoint | None:
        """نزدیک‌ترین مشاهده در یا پیش از یک زمان مشخص."""
        row = self.db.connection.execute(
            """SELECT * FROM price_history
               WHERE slug = ? AND captured_at <= ?
               ORDER BY captured_at DESC LIMIT 1""",
            (slug, timestamp),
        ).fetchone()
        return _to_point(row) if row else None

    def earliest(self, slug: str) -> PricePoint | None:
        """قدیمی‌ترین مشاهده (مبنای «از ابتدای پایش»)."""
        row = self.db.connection.execute(
            "SELECT * FROM price_history WHERE slug = ? ORDER BY captured_at ASC LIMIT 1",
            (slug,),
        ).fetchone()
        return _to_point(row) if row else None

    def series(self, slug: str, *, hours: int = 24, limit: int = 500) -> list[PricePoint]:
        """سری زمانی یک قلم در بازهٔ اخیر."""
        since = time.time() - hours * 3600
        rows = self.db.connection.execute(
            """SELECT * FROM price_history
               WHERE slug = ? AND captured_at >= ?
               ORDER BY captured_at ASC LIMIT ?""",
            (slug, since, limit),
        ).fetchall()
        return [_to_point(r) for r in rows]

    def coverage(self, slug: str) -> tuple[float | None, float | None, int]:
        """بازهٔ پوشش داده: (قدیمی‌ترین، جدیدترین، تعداد)."""
        row = self.db.connection.execute(
            """SELECT MIN(captured_at) AS first, MAX(captured_at) AS last,
                      COUNT(*) AS n
               FROM price_history WHERE slug = ?""",
            (slug,),
        ).fetchone()
        if not row or row["n"] in (None, 0):
            return None, None, 0
        return float(row["first"]), float(row["last"]), int(row["n"])

    def change_since(
        self, slug: str, current_price: float, window_seconds: float
    ) -> tuple[float, float, str] | None:
        """تغییر نسبت به مشاهده‌ای که حدود ``window_seconds`` پیش ثبت شده.

        برمی‌گرداند ``(تغییر مطلق، درصد، توضیح مبنا)`` یا ``None`` اگر
        تاریخچهٔ کافی نداشته باشیم. در حالت ``None`` هیچ عددی ساخته نمی‌شود؛
        لایهٔ نمایش «—» نشان می‌دهد.
        """
        target_time = time.time() - window_seconds
        point = self.price_at_or_before(slug, target_time)
        if point is None:
            return None
        # اگر نزدیک‌ترین مشاهده خیلی دور از هدف باشد (پنجرهٔ خالی)، عدد
        # گمراه‌کننده می‌شود؛ پس فقط بازهٔ معقول را می‌پذیریم.
        drift = abs(target_time - point.captured_at)
        if drift > max(600.0, window_seconds * 0.5):
            return None
        if point.price <= 0:
            return None
        delta = current_price - point.price
        pct = delta / point.price * 100.0
        label = _window_label(window_seconds)
        return delta, pct, label

    def prune(self, retention_days: int) -> int:
        """حذف مشاهده‌های قدیمی‌تر از بازهٔ نگهداری."""
        cutoff = time.time() - retention_days * 86400
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM price_history WHERE captured_at < ?", (cutoff,))
            return cursor.rowcount

    def stats(self) -> dict[str, int]:
        """آمار سبک برای دستور وضعیت."""
        row = self.db.connection.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT slug) AS s FROM price_history"
        ).fetchone()
        return {"points": int(row["n"]), "assets": int(row["s"])}


def _to_point(row: sqlite3.Row) -> PricePoint:
    return PricePoint(
        slug=str(row["slug"]),
        price=float(row["price"]),
        source=str(row["source"]),
        captured_at=float(row["captured_at"]),
        unit=str(row["unit"]),
    )


def _window_label(window_seconds: float) -> str:
    """برچسب فارسی بازهٔ تغییر."""
    hours = window_seconds / 3600
    if abs(hours - 1) < 0.01:
        return "نسبت به ۱ ساعت پیش"
    if abs(hours - 24) < 0.01:
        return "نسبت به ۲۴ ساعت پیش"
    if abs(hours - 168) < 0.01:
        return "نسبت به ۷ روز پیش"
    return f"نسبت به {hours:.0f} ساعت پیش"
