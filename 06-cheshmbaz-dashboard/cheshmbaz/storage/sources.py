# -*- coding: utf-8 -*-
"""ریپازیتوری سلامت منابع.

داشبورد باید وضعیت هر منبع را از **دادهٔ ثبت‌شده** نشان دهد، نه از حافظهٔ
پروسه. دلیلش ساده است: اگر سرویس دوباره راه بیفتد، حافظه خالی می‌شود و
رابط ممکن است به‌غلط همه‌چیز را سالم نشان دهد. این‌جا هر تلاش واکشی ثبت
می‌شود و «آخرین وضعیت شناخته‌شده» از پایگاه داده خوانده می‌شود.
"""
from __future__ import annotations

import time

from ..core.models import SourceStatus


class SourceRepository:
    """ثبت و خواندن وضعیت منابع داده."""

    def __init__(self, storage) -> None:  # noqa: ANN001 - Storage
        self.storage = storage

    # ----------------------------------------------------------------- write
    def record(self, status: SourceStatus) -> SourceStatus:
        """ثبت یک تلاش واکشی (موفق یا ناموفق)."""
        stamp = status.checked_at or time.time()
        with self.storage.transaction() as connection:
            connection.execute(
                "INSERT INTO source_runs (name, ok, latency_ms, items, error, checked_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    status.name, int(status.ok), int(status.latency_ms),
                    int(status.items), status.error or "", stamp,
                ),
            )
        return SourceStatus(
            name=status.name, ok=status.ok, latency_ms=status.latency_ms,
            items=status.items, error=status.error, checked_at=stamp,
        )

    # ------------------------------------------------------------------ read
    def latest(self) -> list[SourceStatus]:
        """آخرین تلاش هر منبع، به‌ترتیب نام."""
        rows = self.storage.query(
            """
            SELECT r.* FROM source_runs AS r
            JOIN (
                SELECT name, MAX(checked_at) AS newest
                FROM source_runs GROUP BY name
            ) AS latest
              ON latest.name = r.name AND latest.newest = r.checked_at
            ORDER BY r.name ASC
            """
        )
        return [
            SourceStatus(
                name=row["name"], ok=bool(row["ok"]), latency_ms=int(row["latency_ms"]),
                items=int(row["items"]), error=row["error"] or "",
                checked_at=row["checked_at"],
            )
            for row in rows
        ]

    def history(self, name: str, *, limit: int = 50) -> list[SourceStatus]:
        """تاریخچهٔ یک منبع، تازه‌ترین‌ها اول."""
        rows = self.storage.query(
            "SELECT * FROM source_runs WHERE name = ? ORDER BY checked_at DESC LIMIT ?",
            (name, max(1, limit)),
        )
        return [
            SourceStatus(
                name=row["name"], ok=bool(row["ok"]), latency_ms=int(row["latency_ms"]),
                items=int(row["items"]), error=row["error"] or "",
                checked_at=row["checked_at"],
            )
            for row in rows
        ]

    def reliability(self, name: str, *, window: int = 50) -> dict:
        """نرخ موفقیت اخیر یک منبع از روی تلاش‌های ثبت‌شده."""
        rows = self.storage.query(
            "SELECT ok, latency_ms FROM source_runs WHERE name = ? "
            "ORDER BY checked_at DESC LIMIT ?",
            (name, max(1, window)),
        )
        total = len(rows)
        if total == 0:
            return {"name": name, "attempts": 0, "success_rate": None, "avg_latency_ms": None}
        okays = sum(1 for row in rows if row["ok"])
        latencies = [int(row["latency_ms"]) for row in rows if row["latency_ms"]]
        return {
            "name": name,
            "attempts": total,
            "success_rate": round(okays / total, 3),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
        }

    def names(self) -> list[str]:
        rows = self.storage.query("SELECT DISTINCT name FROM source_runs ORDER BY name")
        return [row["name"] for row in rows]

    def count(self) -> int:
        row = self.storage.query_one("SELECT COUNT(*) AS n FROM source_runs")
        return int(row["n"]) if row else 0

    def last_checked(self) -> float | None:
        row = self.storage.query_one("SELECT MAX(checked_at) AS m FROM source_runs")
        return float(row["m"]) if row and row["m"] else None


__all__ = ["SourceRepository"]
