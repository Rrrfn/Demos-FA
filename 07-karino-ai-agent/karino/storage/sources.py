# -*- coding: utf-8 -*-
"""مخزن گزارش منابع — تاریخچهٔ سلامت هر منبع.

هر اجرا یک ردیف ثبت می‌کند، حتی اجرای ناموفق. همین جدول است که صفحهٔ
منابع را صادق می‌کند: «آخرین موفقیت: ۳ ساعت پیش» از دادهٔ واقعی می‌آید، نه
از یک فرض. نبود این تاریخچه یعنی وقتی منبعی می‌خوابد، کاربر نمی‌فهمد.
"""
from __future__ import annotations

import time

from .database import connection, init_db


def record(source: str, *, ok: bool, jobs: int = 0, error: str = "",
           duration_ms: int = 0, now: int | None = None) -> None:
    init_db()
    now = int(now if now is not None else time.time())
    with connection() as conn:
        conn.execute(
            """INSERT INTO source_runs (source, ok, jobs, error, duration_ms, ts)
               VALUES (?,?,?,?,?,?)""",
            (source, int(ok), jobs, (error or "")[:400], duration_ms, now))
        # فقط ۵۰ اجرای آخر هر منبع می‌ماند — این جدول لاگ است، نه آرشیو
        conn.execute(
            """DELETE FROM source_runs WHERE source = ? AND id NOT IN (
                   SELECT id FROM source_runs WHERE source = ?
                   ORDER BY ts DESC LIMIT 50)""", (source, source))


def latest_per_source() -> dict:
    """آخرین وضعیت هر منبع به‌همراه زمان آخرین موفقیت."""
    init_db()
    with connection() as conn:
        rows = conn.execute(
            """SELECT r.source, r.ok, r.jobs, r.error, r.duration_ms, r.ts,
                      (SELECT MAX(s.ts) FROM source_runs s
                       WHERE s.source = r.source AND s.ok = 1) AS last_success_ts
               FROM source_runs r
               WHERE r.id IN (SELECT MAX(id) FROM source_runs GROUP BY source)""").fetchall()
    return {row["source"]: row for row in rows}


def history(source: str, limit: int = 30) -> list:
    init_db()
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM source_runs WHERE source = ? ORDER BY ts DESC LIMIT ?",
            (source, limit)).fetchall()


def success_rate(source: str, limit: int = 20) -> float:
    """نرخ موفقیت در آخرین اجراها — برای نمایش سلامت منبع."""
    runs = history(source, limit)
    if not runs:
        return 0.0
    return round(sum(1 for r in runs if r["ok"]) / len(runs), 2)


def recent_errors(limit: int = 10) -> list:
    init_db()
    with connection() as conn:
        return conn.execute(
            """SELECT source, error, ts FROM source_runs
               WHERE ok = 0 AND error != '' ORDER BY ts DESC LIMIT ?""",
            (limit,)).fetchall()
