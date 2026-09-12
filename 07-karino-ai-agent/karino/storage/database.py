# -*- coding: utf-8 -*-
"""اتصال و طرح‌وارهٔ SQLite.

یک اتصال به‌ازای هر عملیات باز و بسته می‌شود (ساده و امن برای چند ریسهٔ
Flask)، ولی حالت WAL و ``timeout`` روشن است تا خواندن هم‌زمان با نوشتن
زمان‌بند پس‌زمینه قفل نخورد.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager

from ..config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,
    external_id   TEXT    NOT NULL,
    fingerprint   TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    company       TEXT    DEFAULT '',
    url           TEXT    DEFAULT '',
    description   TEXT    DEFAULT '',
    tags          TEXT    DEFAULT '[]',
    location      TEXT    DEFAULT '',
    remote        INTEGER DEFAULT 0,
    employment    TEXT    DEFAULT '',
    salary_text   TEXT    DEFAULT '',
    salary_min    REAL,
    salary_max    REAL,
    published_ts  INTEGER,
    first_seen_ts INTEGER NOT NULL,
    last_seen_ts  INTEGER NOT NULL,
    seen_count    INTEGER DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_external ON jobs(source, external_id);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_published  ON jobs(published_ts DESC);

CREATE TABLE IF NOT EXISTS scores (
    job_id      INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    total       INTEGER NOT NULL,
    verdict     TEXT    NOT NULL,
    matched     TEXT    NOT NULL DEFAULT '[]',
    missing     TEXT    NOT NULL DEFAULT '[]',
    factors     TEXT    NOT NULL DEFAULT '[]',
    reasons     TEXT    NOT NULL DEFAULT '[]',
    seniority   TEXT    DEFAULT 'unknown',
    engagement  TEXT    DEFAULT 'unknown',
    scored_ts   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scores_total ON scores(total DESC);

CREATE TABLE IF NOT EXISTS proposals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    tone        TEXT    NOT NULL DEFAULT 'formal',
    variant     TEXT    NOT NULL DEFAULT 'standard',
    writer      TEXT    NOT NULL DEFAULT 'rule_based',
    body        TEXT    NOT NULL,
    created_ts  INTEGER NOT NULL,
    UNIQUE(job_id, tone, variant)
);

CREATE TABLE IF NOT EXISTS saved (
    job_id      INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    note        TEXT DEFAULT '',
    created_ts  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    ok          INTEGER NOT NULL,
    jobs        INTEGER DEFAULT 0,
    error       TEXT    DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    ts          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_runs ON source_runs(source, ts DESC);

CREATE TABLE IF NOT EXISTS activity (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,
    level       TEXT    NOT NULL DEFAULT 'info',
    message     TEXT    NOT NULL,
    meta        TEXT    DEFAULT '{}',
    ts          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(ts DESC);
"""

_local = threading.local()


def db_path() -> str:
    return get_settings().db_path


@contextmanager
def connection():
    """اتصال با تأیید تقویم (commit) یا بازگشت (rollback) خودکار."""
    path = db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_initialized = False


def init_db(force: bool = False) -> None:
    """ساخت طرح‌واره — بی‌اثر اگر قبلاً انجام شده باشد (مگر ``force``)."""
    global _initialized
    if _initialized and not force:
        return
    with connection() as conn:
        conn.executescript(_SCHEMA)
    _initialized = True


def reset_init_flag() -> None:
    """برای تست‌ها — تا با مسیر پایگاه دادهٔ تازه، طرح‌واره دوباره ساخته شود."""
    global _initialized
    _initialized = False
