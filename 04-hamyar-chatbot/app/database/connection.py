# -*- coding: utf-8 -*-
"""SQLite connection handling and first-run initialisation.

The database file lives outside the package (``data/``), so the same code runs
in development, tests and production by pointing ``HAMYAR_DB_PATH`` elsewhere.
"""
from __future__ import annotations

import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import Config

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def resolve_db_path() -> Path:
    """Resolve the database path from the active Flask config when available."""
    try:  # Imported lazily so plain scripts can use this module too.
        from flask import current_app

        if current_app:
            return Path(current_app.config["DB_PATH"])
    except (ImportError, RuntimeError):
        pass
    return Path(Config.DB_PATH)


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a tuned SQLite connection with row access by column name."""
    target = Path(path or resolve_db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Transactional connection scope: commit on success, roll back on error."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not exist yet."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def initialize_database(path: Path | None = None, seed: bool = True) -> Path:
    """Create the schema and seed the knowledge base on an empty database.

    Safe to call on every start: it never overwrites existing data.
    """
    from app.database.repository import FaqRepository
    from app.seeds import FAQ_SEEDS

    target = Path(path or resolve_db_path())
    with session(target) as conn:
        apply_schema(conn)
        if seed:
            count = conn.execute("SELECT COUNT(*) FROM faq").fetchone()[0]
            if count == 0:
                repo = FaqRepository(conn)
                for seed_faq in FAQ_SEEDS:
                    repo.create(
                        question=seed_faq.question,
                        answer=seed_faq.answer,
                        category=seed_faq.category,
                        variants=list(seed_faq.variants),
                    )
                logger.info("seeded %d knowledge-base entries", len(FAQ_SEEDS))
    return target
