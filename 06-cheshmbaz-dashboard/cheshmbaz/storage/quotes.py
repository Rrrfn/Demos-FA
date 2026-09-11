# -*- coding: utf-8 -*-
"""ریپازیتوری آخرین وضعیت قیمت‌ها.

هر ردیف ``quotes`` هم قیمت جاری را دارد و هم قیمت قبلی؛ بنابراین «تغییر»
بدون اسکن تاریخچه محاسبه می‌شود. نوشتن روی ردیف موجود، قیمت فعلی را به
«قبلی» منتقل می‌کند — ولی فقط اگر مشاهدهٔ تازه واقعاً جدیدتر باشد، تا نمونهٔ
تکراری قیمت قبلی را خراب نکند.
"""
from __future__ import annotations

import time

from ..core.models import Freshness, Quote

_COLUMNS = (
    "slug", "price", "unit", "source", "observed_at", "fetched_at",
    "day_low", "day_high", "change_abs", "change_pct", "change_basis",
    "previous_price", "previous_at", "updated_at",
)


class QuoteRepository:
    """خواندن و نوشتن آخرین وضعیت هر دارایی."""

    def __init__(self, storage) -> None:  # noqa: ANN001 - Storage
        self.storage = storage

    # ------------------------------------------------------------------ read
    @staticmethod
    def _to_quote(row) -> Quote:  # noqa: ANN001 - sqlite3.Row
        quote = Quote(
            slug=row["slug"],
            price=row["price"],
            unit=row["unit"],
            source=row["source"],
            observed_at=row["observed_at"],
            fetched_at=row["fetched_at"],
            day_low=row["day_low"],
            day_high=row["day_high"],
            change_abs=row["change_abs"],
            change_pct=row["change_pct"],
            change_basis=row["change_basis"] or "",
            previous_price=row["previous_price"],
            previous_at=row["previous_at"],
        )
        return quote

    def get(self, slug: str) -> Quote | None:
        row = self.storage.query_one("SELECT * FROM quotes WHERE slug = ?", (slug,))
        return self._to_quote(row) if row else None

    def get_many(self, slugs: list[str]) -> dict[str, Quote]:
        if not slugs:
            return {}
        marks = ",".join("?" for _ in slugs)
        rows = self.storage.query(f"SELECT * FROM quotes WHERE slug IN ({marks})", tuple(slugs))
        return {row["slug"]: self._to_quote(row) for row in rows}

    def all(self) -> dict[str, Quote]:
        rows = self.storage.query("SELECT * FROM quotes")
        return {row["slug"]: self._to_quote(row) for row in rows}

    def count(self) -> int:
        row = self.storage.query_one("SELECT COUNT(*) AS n FROM quotes")
        return int(row["n"]) if row else 0

    def last_update(self) -> float | None:
        """زمان آخرین نوشتن موفق در جدول قیمت‌ها."""
        row = self.storage.query_one("SELECT MAX(updated_at) AS m FROM quotes")
        return float(row["m"]) if row and row["m"] else None

    # ----------------------------------------------------------------- write
    def save_many(self, quotes: dict[str, Quote]) -> int:
        """نوشتن گروهی.

        اگر ``Quote`` قیمت قبلی را حمل نکند، از ردیف موجود پر می‌شود. اگر
        مشاهدهٔ تازه قدیمی‌تر یا برابر مشاهدهٔ ذخیره‌شده باشد، چیزی نوشته
        نمی‌شود (جلوگیری از رکورد تکراری).
        """
        if not quotes:
            return 0
        existing = self.get_many(list(quotes))
        now = time.time()
        written = 0
        rows = []
        for slug, quote in quotes.items():
            old = existing.get(slug)
            if old is not None and quote.observed_at and quote.observed_at <= old.observed_at:
                continue
            previous_price = quote.previous_price
            previous_at = quote.previous_at
            if previous_price is None and old is not None:
                previous_price = old.price
                previous_at = old.observed_at
            rows.append((
                slug, quote.price, quote.unit, quote.source, quote.observed_at,
                quote.fetched_at or now, quote.day_low, quote.day_high,
                quote.change_abs, quote.change_pct, quote.change_basis or "",
                previous_price, previous_at, now,
            ))
            written += 1

        if not rows:
            return 0

        marks = ",".join("?" for _ in _COLUMNS)
        with self.storage.transaction() as connection:
            connection.executemany(
                f"INSERT INTO quotes ({','.join(_COLUMNS)}) VALUES ({marks}) "
                "ON CONFLICT(slug) DO UPDATE SET "
                + ", ".join(f"{column} = excluded.{column}" for column in _COLUMNS if column != "slug"),
                rows,
            )
        return written

    def mark_freshness(self, live_within: int, stale_after: int, expire_after: int) -> None:
        """اعلام وضعیت تازگی — محاسبه‌شده، نه ذخیره‌شده.

        این متد برای سازگاری است؛ وضعیت تازگی در زمان خواندن و از روی سن
        داده تعیین می‌شود تا هرگز برچسب کهنه روی دادهٔ تازه نماند.
        """
        return None


__all__ = ["QuoteRepository", "Freshness"]
