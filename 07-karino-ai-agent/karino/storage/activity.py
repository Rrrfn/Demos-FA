# -*- coding: utf-8 -*-
"""مخزن فعالیت — رویدادهایی که کاربر باید ببیند.

«لاگ» برای برنامه‌نویس است و در فایل می‌ماند؛ «فعالیت» برای کاربر است و در
داشبورد دیده می‌شود: هر دور جمع‌آوری، هر منبعی که خطا داد، هر پیشنهادی که
ساخته شد، هر هشداری که ثبت شد. بدون این، سامانه یک جعبهٔ سیاه است که گاهی
آگهی تازه دارد و گاهی ندارد.
"""
from __future__ import annotations

import json
import time

from .database import connection, init_db

LEVELS = ("info", "success", "warning", "error")


def log(kind: str, message: str, *, level: str = "info", meta: dict | None = None,
        now: int | None = None) -> int:
    init_db()
    now = int(now if now is not None else time.time())
    if level not in LEVELS:
        level = "info"
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO activity (kind, level, message, meta, ts) VALUES (?,?,?,?,?)",
            (kind, level, message[:400], json.dumps(meta or {}, ensure_ascii=False), now))
        # نگه‌داشتن ۳۰۰ رویداد آخر
        conn.execute(
            """DELETE FROM activity WHERE id NOT IN (
                   SELECT id FROM activity ORDER BY ts DESC LIMIT 300)""")
        return int(cur.lastrowid)


def recent(limit: int = 40, *, level: str = "") -> list:
    init_db()
    with connection() as conn:
        if level:
            return conn.execute(
                "SELECT * FROM activity WHERE level = ? ORDER BY ts DESC LIMIT ?",
                (level, limit)).fetchall()
        return conn.execute("SELECT * FROM activity ORDER BY ts DESC LIMIT ?",
                            (limit,)).fetchall()


def grouped(limit: int = 40) -> list[dict]:
    """رویدادها با ``meta`` رمزگشایی‌شده — آمادهٔ رندر در قالب."""
    out: list[dict] = []
    for row in recent(limit):
        try:
            meta = json.loads(row["meta"] or "{}")
        except (ValueError, TypeError):
            meta = {}
        out.append({
            "id": row["id"], "kind": row["kind"], "level": row["level"],
            "message": row["message"], "ts": row["ts"], "meta": meta,
        })
    return out


def count_by_level() -> dict:
    init_db()
    result = {level: 0 for level in LEVELS}
    with connection() as conn:
        for row in conn.execute("SELECT level, COUNT(*) AS n FROM activity GROUP BY level"):
            result[row["level"]] = int(row["n"])
    return result


def clear() -> int:
    init_db()
    with connection() as conn:
        return conn.execute("DELETE FROM activity").rowcount or 0
