# -*- coding: utf-8 -*-
"""مخزن آگهی‌ها — درج، فیلتر، صفحه‌بندی و پاک‌سازی.

فیلترها همه در SQL بسته می‌شوند (نه در پایتون) تا صفحه‌بندی روی کل مجموعه
درست کار کند؛ وگرنه «صفحهٔ ۳ از ۵۰۰ رکورد» روی زیرمجموعهٔ بارگذاری‌شده
حساب می‌شد و نتیجه گمراه‌کننده بود.
"""
from __future__ import annotations

import json
import sqlite3
import time

from ..core.models import Job
from .database import connection, init_db

SORT_OPTIONS = {
    "score": "s.total DESC, COALESCE(j.published_ts, j.first_seen_ts) DESC",
    "published": "COALESCE(j.published_ts, j.first_seen_ts) DESC",
    "recent": "j.first_seen_ts DESC",
    "oldest": "COALESCE(j.published_ts, j.first_seen_ts) ASC",
    "company": "j.company COLLATE NOCASE ASC, s.total DESC",
}
DEFAULT_SORT = "score"


#: ستون‌های درج — یک جا تعریف شده تا فهرست ستون و مقادیر از هم جدا نیفتند
_INSERT_COLUMNS = (
    "source, external_id, fingerprint, title, company, url, description, tags, "
    "location, remote, employment, salary_text, salary_min, salary_max, "
    "published_ts, first_seen_ts, last_seen_ts, seen_count")
_INSERT_SQL = (f"INSERT INTO jobs ({_INSERT_COLUMNS}) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)")

#: به‌روزرسانی رکورد موجود. مقادیر بودجه و تاریخ با ``COALESCE`` نگه داشته
#: می‌شوند: نسخهٔ بعدی آگهی ممکن است این فیلدها را نداشته باشد و پاک‌کردن
#: دادهٔ قبلی، اطلاعات را از دست می‌دهد.
_TOUCH_SQL = ("""UPDATE jobs SET last_seen_ts = ?, seen_count = seen_count + 1,
                          title = ?, description = ?, tags = ?, url = ?,
                          company = ?, location = ?, remote = ?,
                          salary_text = ?, salary_min = COALESCE(?, salary_min),
                          salary_max = COALESCE(?, salary_max),
                          published_ts = COALESCE(?, published_ts)
                   WHERE id = ?""")


def upsert(job: Job, *, now: int | None = None) -> tuple[int, bool]:
    """درج آگهی تازه یا به‌روزرسانی رکورد موجود.

    برگشت: ``(job_id, is_new)``. تکرار (همان منبع و شناسه) رکورد را دوباره
    نمی‌سازد؛ فقط ``last_seen_ts`` و شمارندهٔ مشاهده بالا می‌رود، چون «این
    آگهی هنوز باز است» خودش یک سیگنال است.
    """
    init_db()
    now = int(now if now is not None else time.time())

    with connection() as conn:
        row = conn.execute(
            "SELECT id FROM jobs WHERE source = ? AND external_id = ?",
            (job.source, job.external_id)).fetchone()

        if row:
            _touch(conn, job, now, int(row["id"]))
            return int(row["id"]), False

        return _insert_or_touch(conn, job, now)


def _touch(conn, job: Job, now: int, job_id: int) -> None:
    """ثبت «این آگهی هنوز دیده می‌شود» و تازه‌سازی محتوایش."""
    conn.execute(_TOUCH_SQL, (
        now, job.title, job.description, json.dumps(job.tags, ensure_ascii=False),
        job.url, job.company, job.location, int(job.remote), job.salary_text,
        job.salary_min, job.salary_max, job.published_ts, job_id))


def _insert_or_touch(conn, job: Job, now: int) -> tuple[int, bool]:
    """درج رکورد تازه؛ اگر دیگری زودتر درج کرده باشد، همان را به‌روز می‌کند.

    چرا لازم است: دو کارگر وب می‌توانند هم‌زمان یک دور جمع‌آوری را شروع کنند
    (مثلاً هر دو هنگام راه‌اندازی). فاصلهٔ میان «بررسی وجود» و «درج» یک بازهٔ
    مسابقه است؛ در آن حالت درج دوم قید یکتایی ``(source, external_id)`` را
    می‌شکند و کل دور جمع‌آوری را با خطا برمی‌گرداند — به‌خاطر چیزی که اصلاً
    مسئله نیست.
    """
    try:
        cur = conn.execute(_INSERT_SQL, (
            job.source, job.external_id, job.fingerprint, job.title, job.company,
            job.url, job.description, json.dumps(job.tags, ensure_ascii=False),
            job.location, int(job.remote), job.employment, job.salary_text,
            job.salary_min, job.salary_max, job.published_ts, now, now))
        return int(cur.lastrowid), True
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT id FROM jobs WHERE source = ? AND external_id = ?",
            (job.source, job.external_id)).fetchone()
        if row is None:
            raise
        _touch(conn, job, now, int(row["id"]))
        return int(row["id"]), False


def get(job_id: int):
    init_db()
    with connection() as conn:
        return conn.execute(
            """SELECT j.*, s.total, s.verdict, s.matched, s.missing, s.factors,
                      s.reasons, s.seniority, s.engagement AS score_engagement,
                      (SELECT 1 FROM saved v WHERE v.job_id = j.id) AS is_saved,
                      (SELECT COUNT(*) FROM proposals p WHERE p.job_id = j.id) AS proposal_count
               FROM jobs j LEFT JOIN scores s ON s.job_id = j.id
               WHERE j.id = ?""", (job_id,)).fetchone()


def query(*, q: str = "", min_score: int = 0, max_score: int = 100,
          source: str = "", remote: bool | None = None,
          saved_only: bool = False, sort: str = DEFAULT_SORT,
          page: int = 1, per_page: int = 20, include_unscored: bool = True):
    """فهرست آگهی‌ها با فیلترهای ترکیبی و صفحه‌بندی.

    برگشت: ``(rows, total)`` که ``total`` شمار کل نتایج *پیش از* صفحه‌بندی است.
    """
    init_db()
    where, params = _build_where(q=q, min_score=min_score, max_score=max_score,
                                 source=source, remote=remote,
                                 saved_only=saved_only,
                                 include_unscored=include_unscored)
    order = SORT_OPTIONS.get(sort, SORT_OPTIONS[DEFAULT_SORT])
    offset = max(0, (page - 1) * per_page)

    base = "FROM jobs j LEFT JOIN scores s ON s.job_id = j.id"
    with connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) {base} WHERE {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT j.id, j.source, j.title, j.company, j.url, j.location,
                       j.remote, j.employment, j.salary_text, j.tags,
                       j.published_ts, j.first_seen_ts, j.seen_count,
                       COALESCE(s.total, -1) AS total, COALESCE(s.verdict, '') AS verdict,
                       COALESCE(s.matched, '[]') AS matched,
                       COALESCE(s.factors, '[]') AS factors,
                       COALESCE(s.reasons, '[]') AS reasons,
                       COALESCE(s.seniority, 'unknown') AS seniority,
                       (SELECT 1 FROM saved v WHERE v.job_id = j.id) AS is_saved,
                       (SELECT COUNT(*) FROM proposals p WHERE p.job_id = j.id) AS proposal_count
                {base} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?""",
            (*params, per_page, offset)).fetchall()
    return rows, int(total)


def _build_where(*, q: str, min_score: int, max_score: int, source: str,
                 remote: bool | None, saved_only: bool,
                 include_unscored: bool) -> tuple[str, tuple]:
    clauses = ["1=1"]
    params: list = []

    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ? OR j.tags LIKE ?)")
        params.extend([like, like, like, like])
    if min_score > 0:
        clauses.append("s.total >= ?")
        params.append(min_score)
    if max_score < 100:
        clauses.append("s.total <= ?")
        params.append(max_score)
    if source:
        clauses.append("j.source = ?")
        params.append(source)
    if remote is not None:
        clauses.append("j.remote = ?")
        params.append(int(remote))
    if saved_only:
        clauses.append("EXISTS (SELECT 1 FROM saved v WHERE v.job_id = j.id)")
    if not include_unscored:
        clauses.append("s.job_id IS NOT NULL")

    return " AND ".join(clauses), tuple(params)


def existing_fingerprints() -> set[str]:
    init_db()
    with connection() as conn:
        rows = conn.execute("SELECT DISTINCT fingerprint FROM jobs").fetchall()
    return {row["fingerprint"] for row in rows if row["fingerprint"]}


def fingerprint_by_external(source: str, external_id: str) -> str | None:
    init_db()
    with connection() as conn:
        row = conn.execute("SELECT fingerprint FROM jobs WHERE source = ? AND external_id = ?",
                           (source, external_id)).fetchone()
    return row["fingerprint"] if row else None


def by_ids(job_ids: list[int]) -> list:
    if not job_ids:
        return []
    init_db()
    marks = ",".join("?" * len(job_ids))
    with connection() as conn:
        return conn.execute(f"SELECT * FROM jobs WHERE id IN ({marks})", tuple(job_ids)).fetchall()


def count() -> int:
    init_db()
    with connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])


def count_since(ts: int) -> int:
    init_db()
    with connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM jobs WHERE first_seen_ts >= ?",
                                (ts,)).fetchone()[0])


def prune(*, max_jobs: int, max_age_days: int, now: int | None = None) -> dict:
    """پاک‌سازی: آگهی‌های خیلی کهنه و سرریز سقف ظرفیت.

    رکوردهای «ذخیره‌شده» هرگز پاک نمی‌شوند — تصمیم کاربر بر سقف ظرفیت
    اولویت دارد.
    """
    init_db()
    now = int(now if now is not None else time.time())
    removed_age = removed_cap = 0

    with connection() as conn:
        cur = conn.execute(
            """DELETE FROM jobs WHERE published_ts IS NOT NULL AND published_ts < ?
               AND id NOT IN (SELECT job_id FROM saved)""",
            (now - max_age_days * 86_400,))
        removed_age = cur.rowcount or 0

        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if total > max_jobs:
            overflow = total - max_jobs
            cur = conn.execute(
                """DELETE FROM jobs WHERE id IN (
                       SELECT id FROM jobs
                       WHERE id NOT IN (SELECT job_id FROM saved)
                       ORDER BY COALESCE(published_ts, first_seen_ts) ASC
                       LIMIT ?)""", (overflow,))
            removed_cap = cur.rowcount or 0

    return {"removed_stale": removed_age, "removed_overflow": removed_cap}


def source_breakdown() -> list:
    """تعداد آگهی به تفکیک منبع — برای صفحهٔ منابع و نمای کلی."""
    init_db()
    with connection() as conn:
        return conn.execute(
            """SELECT source, COUNT(*) AS jobs,
                      SUM(CASE WHEN remote = 1 THEN 1 ELSE 0 END) AS remote
               FROM jobs GROUP BY source ORDER BY jobs DESC""").fetchall()
