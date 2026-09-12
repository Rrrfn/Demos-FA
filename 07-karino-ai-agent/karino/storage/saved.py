# -*- coding: utf-8 -*-
"""مخزن فهرست ذخیره‌شده — انتخاب کاربر، جدا از امتیاز الگوریتم."""
from __future__ import annotations

import time

from .database import connection, init_db


def add(job_id: int, note: str = "", *, now: int | None = None) -> bool:
    """افزودن به فهرست. برگشت ``True`` اگر تازه افزوده شد."""
    init_db()
    now = int(now if now is not None else time.time())
    with connection() as conn:
        exists = conn.execute("SELECT 1 FROM saved WHERE job_id = ?", (job_id,)).fetchone()
        if exists:
            return False
        conn.execute("INSERT INTO saved (job_id, note, created_ts) VALUES (?,?,?)",
                     (job_id, note, now))
        return True


def remove(job_id: int) -> bool:
    init_db()
    with connection() as conn:
        cur = conn.execute("DELETE FROM saved WHERE job_id = ?", (job_id,))
        return (cur.rowcount or 0) > 0


def is_saved(job_id: int) -> bool:
    init_db()
    with connection() as conn:
        return conn.execute("SELECT 1 FROM saved WHERE job_id = ?", (job_id,)).fetchone() is not None


def toggle(job_id: int) -> bool:
    """برگشت وضعیت تازه: ``True`` یعنی اکنون ذخیره‌شده است."""
    if is_saved(job_id):
        remove(job_id)
        return False
    add(job_id)
    return True


def count() -> int:
    init_db()
    with connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM saved").fetchone()[0])
