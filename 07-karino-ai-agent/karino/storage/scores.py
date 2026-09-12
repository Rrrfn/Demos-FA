# -*- coding: utf-8 -*-
"""مخزن امتیازها — نتیجهٔ کامل تحلیل تطابق را نگه می‌دارد.

کل ``factors`` سریال‌شده ذخیره می‌شود، نه فقط عدد کل: صفحهٔ «تحلیل تطابق»
باید بعداً هم بتواند دقیقاً همان توضیحی را نشان دهد که در لحظهٔ امتیازدهی
ساخته شد. اگر فقط عدد ذخیره می‌کردیم، توضیح هر بار از نو ساخته می‌شد و
ممکن بود با عدد ذخیره‌شده ناهم‌خوان شود.
"""
from __future__ import annotations

import json
import time

from ..core.models import ScoreResult
from .database import connection, init_db


def save(job_id: int, result: ScoreResult, *, now: int | None = None) -> None:
    init_db()
    now = int(now if now is not None else time.time())
    with connection() as conn:
        conn.execute(
            """INSERT INTO scores (job_id, total, verdict, matched, missing,
                     factors, reasons, seniority, engagement, scored_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET
                     total = excluded.total, verdict = excluded.verdict,
                     matched = excluded.matched, missing = excluded.missing,
                     factors = excluded.factors, reasons = excluded.reasons,
                     seniority = excluded.seniority,
                     engagement = excluded.engagement,
                     scored_ts = excluded.scored_ts""",
            (job_id, result.total, result.verdict,
             json.dumps(result.matched_skills, ensure_ascii=False),
             json.dumps(result.missing_skills, ensure_ascii=False),
             json.dumps([f.to_dict() for f in result.factors], ensure_ascii=False),
             json.dumps(result.reasons, ensure_ascii=False),
             result.seniority, result.engagement, now))


def get(job_id: int):
    init_db()
    with connection() as conn:
        return conn.execute("SELECT * FROM scores WHERE job_id = ?", (job_id,)).fetchone()


def unscored_job_ids(limit: int = 500) -> list[int]:
    """آگهی‌هایی که هنوز امتیاز نگرفته‌اند — ورودی دور تکمیلی خط لوله."""
    init_db()
    with connection() as conn:
        rows = conn.execute(
            """SELECT j.id FROM jobs j LEFT JOIN scores s ON s.job_id = j.id
               WHERE s.job_id IS NULL ORDER BY j.first_seen_ts DESC LIMIT ?""",
            (limit,)).fetchall()
    return [int(r["id"]) for r in rows]


def distribution() -> dict:
    """توزیع امتیاز در سطل‌های ده‌تایی — برای نمودار نمای کلی."""
    init_db()
    buckets = {"0-39": 0, "40-54": 0, "55-71": 0, "72-84": 0, "85-100": 0}
    with connection() as conn:
        rows = conn.execute("SELECT total FROM scores").fetchall()
        for row in rows:
            total = row["total"]
            if total >= 85:
                buckets["85-100"] += 1
            elif total >= 72:
                buckets["72-84"] += 1
            elif total >= 55:
                buckets["55-71"] += 1
            elif total >= 40:
                buckets["40-54"] += 1
            else:
                buckets["0-39"] += 1
    return buckets


def average() -> float:
    init_db()
    with connection() as conn:
        row = conn.execute("SELECT AVG(total) AS avg FROM scores").fetchone()
    return round(float(row["avg"] or 0), 1)
