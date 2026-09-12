# -*- coding: utf-8 -*-
"""مخزن پیشنهادها — هر آگهی می‌تواند چند نسخه داشته باشد.

کلید یکتایی ``(job_id, tone, variant)`` است، چون یک آگهی می‌تواند پیشنهاد
رسمی، کوتاه و مشورتی داشته باشد. ذخیره‌سازی نسخه‌ها هم سرعت می‌دهد و هم
جلوی هزینهٔ تکراری LLM را می‌گیرد.
"""
from __future__ import annotations

import time

from .database import connection, init_db


def save(job_id: int, body: str, writer: str, *, tone: str = "formal",
         variant: str = "standard", now: int | None = None) -> int:
    init_db()
    now = int(now if now is not None else time.time())
    with connection() as conn:
        conn.execute(
            """INSERT INTO proposals (job_id, tone, variant, writer, body, created_ts)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(job_id, tone, variant) DO UPDATE SET
                     body = excluded.body, writer = excluded.writer,
                     created_ts = excluded.created_ts""",
            (job_id, tone, variant, writer, body, now))
        row = conn.execute(
            "SELECT id FROM proposals WHERE job_id = ? AND tone = ? AND variant = ?",
            (job_id, tone, variant)).fetchone()
    return int(row["id"])


def get(job_id: int, *, tone: str = "formal", variant: str = "standard"):
    init_db()
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM proposals WHERE job_id = ? AND tone = ? AND variant = ?",
            (job_id, tone, variant)).fetchone()


def list_for_job(job_id: int) -> list:
    init_db()
    with connection() as conn:
        return conn.execute(
            "SELECT tone, variant, writer, created_ts FROM proposals WHERE job_id = ? ORDER BY created_ts DESC",
            (job_id,)).fetchall()


def latest_for_job(job_id: int):
    init_db()
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM proposals WHERE job_id = ? ORDER BY created_ts DESC LIMIT 1",
            (job_id,)).fetchone()


def delete(job_id: int, *, tone: str | None = None, variant: str | None = None) -> int:
    init_db()
    with connection() as conn:
        if tone and variant:
            cur = conn.execute("DELETE FROM proposals WHERE job_id = ? AND tone = ? AND variant = ?",
                               (job_id, tone, variant))
        else:
            cur = conn.execute("DELETE FROM proposals WHERE job_id = ?", (job_id,))
        return cur.rowcount or 0


def count() -> int:
    init_db()
    with connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0])


def recent(limit: int = 8) -> list:
    init_db()
    with connection() as conn:
        return conn.execute(
            """SELECT p.job_id, p.tone, p.variant, p.writer, p.created_ts,
                      j.title, j.company
               FROM proposals p JOIN jobs j ON j.id = p.job_id
               ORDER BY p.created_ts DESC LIMIT ?""", (limit,)).fetchall()
