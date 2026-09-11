# -*- coding: utf-8 -*-
"""ریپازیتوری سری زمانی قیمت.

نمودارها فقط از همین جدول ساخته می‌شوند؛ هیچ‌جا دادهٔ تولیدی یا درون‌یابی‌شده
به نمودار تزریق نمی‌شود. اگر بازه‌ای داده نداشته باشد، نمودار صادقانه خالی
می‌ماند و رابط پیام «دادهٔ کافی نیست» نشان می‌دهد.
"""
from __future__ import annotations

import time

from ..core.models import HistoryRange, Quote, SeriesPoint

#: بازه‌های قابل انتخاب در رابط کاربری
RANGES: tuple[HistoryRange, ...] = (
    HistoryRange("1D", "۲۴ ساعت", 86_400, 300, 240),
    HistoryRange("7D", "۷ روز", 604_800, 1_800, 260),
    HistoryRange("30D", "۳۰ روز", 2_592_000, 7_200, 280),
    HistoryRange("90D", "۹۰ روز", 7_776_000, 21_600, 300),
)

_RANGE_BY_KEY = {item.key: item for item in RANGES}


def resolve_range(key: str | None) -> HistoryRange:
    """بازه را از کلید می‌خواند؛ کلید ناشناخته به بازهٔ پیش‌فرض می‌افتد."""
    if not key:
        return _RANGE_BY_KEY["7D"]
    return _RANGE_BY_KEY.get(key.strip().upper(), _RANGE_BY_KEY["7D"])


class HistoryRepository:
    """ثبت و خواندن سری زمانی."""

    def __init__(self, storage) -> None:  # noqa: ANN001 - Storage
        self.storage = storage

    # ----------------------------------------------------------------- write
    def record_many(self, quotes: dict[str, Quote]) -> int:
        """ثبت مشاهدات تازه.

        رکوردی که برای همان قلم زمان مشاهدهٔ کوچک‌تر یا مساوی آخرین رکورد
        داشته باشد نوشته نمی‌شود؛ همین قاعده از تکرار رکورد در دورهای پشت‌سرهم
        که منبع هنوز زمان تازه‌ای منتشر نکرده جلوگیری می‌کند.
        """
        if not quotes:
            return 0
        slugs = list(quotes)
        marks = ",".join("?" for _ in slugs)
        latest_rows = self.storage.query(
            f"SELECT slug, MAX(observed_at) AS last_seen FROM readings "
            f"WHERE slug IN ({marks}) GROUP BY slug",
            tuple(slugs),
        )
        latest = {row["slug"]: row["last_seen"] for row in latest_rows}

        rows = []
        for slug, quote in quotes.items():
            last_seen = latest.get(slug)
            if last_seen is not None and quote.observed_at <= last_seen:
                continue
            rows.append((
                slug, quote.price, quote.unit, quote.source,
                quote.observed_at, quote.fetched_at or time.time(),
            ))

        if not rows:
            return 0
        with self.storage.transaction() as connection:
            connection.executemany(
                "INSERT INTO readings (slug, price, unit, source, observed_at, fetched_at) "
                "VALUES (?,?,?,?,?,?)",
                rows,
            )
        return len(rows)

    # ------------------------------------------------------------------ read
    def series(
        self, slug: str, *, range_key: str | None = None, max_points: int | None = None
    ) -> tuple[HistoryRange, list[SeriesPoint]]:
        """سری زمانی سطل‌بندی‌شده برای یک بازه.

        سطل‌بندی با میانگین انجام می‌شود و تعداد نقاط را برای نمودار سبک
        نگه می‌دارد، بدون تغییر در ماهیت داده.
        """
        window = resolve_range(range_key)
        limit = max_points or window.max_points
        since = time.time() - window.seconds
        bucket = max(60, int(window.seconds // max(1, limit)))

        rows = self.storage.query(
            """
            SELECT CAST(observed_at / :bucket AS INTEGER) * :bucket AS bucket_ts,
                   AVG(price) AS avg_price,
                   COUNT(*) AS samples
            FROM readings
            WHERE slug = :slug AND observed_at >= :since
            GROUP BY bucket_ts
            ORDER BY bucket_ts ASC
            """,
            {"bucket": bucket, "slug": slug, "since": since},
        )
        points = [
            SeriesPoint(ts=float(row["bucket_ts"]), price=float(row["avg_price"]),
                        samples=int(row["samples"]))
            for row in rows
        ]
        return window, points

    def reference(
        self, slug: str, *, seconds: int = 86_400
    ) -> tuple[float, float] | None:
        """قیمت مرجع برای محاسبهٔ تغییر.

        نزدیک‌ترین مشاهده به «الان منهای بازه» انتخاب می‌شود؛ اگر چنین
        مشاهده‌ای نباشد، قدیمی‌ترین مشاهدهٔ داخل بازه. خروجی ``(قیمت، زمان)``
        یا ``None`` وقتی هیچ مشاهده‌ای در بازه نیست — که یعنی درصد تغییر
        باید «—» بماند، نه صفر.
        """
        cutoff = time.time() - seconds
        row = self.storage.query_one(
            "SELECT price, observed_at FROM readings WHERE slug = ? AND observed_at <= ? "
            "ORDER BY observed_at DESC LIMIT 1",
            (slug, cutoff),
        )
        if row is None:
            row = self.storage.query_one(
                "SELECT price, observed_at FROM readings WHERE slug = ? AND observed_at >= ? "
                "ORDER BY observed_at ASC LIMIT 1",
                (slug, cutoff),
            )
        if row is None:
            return None
        return float(row["price"]), float(row["observed_at"])

    def coverage(self, slug: str) -> dict:
        """پوشش دادهٔ ثبت‌شده برای یک قلم."""
        row = self.storage.query_one(
            "SELECT COUNT(*) AS n, MIN(observed_at) AS first_seen, "
            "MAX(observed_at) AS last_seen FROM readings WHERE slug = ?",
            (slug,),
        )
        if not row or not row["n"]:
            return {"points": 0, "first_seen": None, "last_seen": None, "span_hours": 0.0}
        span = (row["last_seen"] - row["first_seen"]) / 3600 if row["first_seen"] else 0.0
        return {
            "points": int(row["n"]),
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "span_hours": round(span, 2),
        }

    def available_ranges(self, slug: str) -> list[dict]:
        """چه بازه‌هایی برای این قلم واقعاً داده دارند؟"""
        coverage = self.coverage(slug)
        span = coverage["span_hours"] * 3600
        out = []
        for item in RANGES:
            usable = coverage["points"] >= 3 and span >= min(item.seconds * 0.5, item.seconds)
            out.append({
                "key": item.key,
                "label": item.label,
                "seconds": item.seconds,
                "points": coverage["points"],
                "has_data": bool(usable and coverage["points"] >= 2),
            })
        return out

    def point_counts(self) -> dict[str, int]:
        """تعداد نمونه‌های هر قلم در تاریخچه — برای نشان تازگی نمودار."""
        rows = self.storage.query("SELECT slug, COUNT(*) AS n FROM readings GROUP BY slug")
        return {row["slug"]: int(row["n"]) for row in rows}

    def stats(self) -> dict:
        row = self.storage.query_one(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT slug) AS assets FROM readings"
        )
        return {
            "points": int(row["n"]) if row else 0,
            "assets": int(row["assets"]) if row else 0,
        }


__all__ = ["RANGES", "HistoryRepository", "resolve_range"]
