# -*- coding: utf-8 -*-
"""Data-access layer.

Each repository receives an open connection, so the service layer decides where
the transaction boundaries are. No SQL leaks into routes or templates.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

from app.models import ConversationTurn, Faq, HandoffRequest, KbEntry

FAQ_COLUMNS = "id, question, answer, category, created_at, updated_at"


def _faq_from_row(row: sqlite3.Row, variants: Sequence[str] = ()) -> Faq:
    """Build a Faq entity from a row plus its variant list."""
    return Faq(
        id=row["id"],
        question=row["question"],
        answer=row["answer"],
        category=row["category"],
        variants=tuple(variants),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _turn_from_row(row: sqlite3.Row) -> ConversationTurn:
    """Build a ConversationTurn entity from a row."""
    return ConversationTurn(
        id=row["id"],
        session_id=row["session_id"],
        user_text=row["user_text"],
        matched_faq_id=row["matched_faq_id"],
        matched_text=row["matched_text"],
        score=row["score"],
        confidence=row["confidence"],
        answered=bool(row["answered"]),
        category=row["category"],
        feedback=row["feedback"],
        latency_ms=row["latency_ms"],
        created_at=row["created_at"],
    )


class FaqRepository:
    """CRUD and lookups for the knowledge base."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------------ reads
    def get(self, faq_id: int) -> Faq | None:
        """Return a single FAQ including its variants."""
        row = self.conn.execute(
            f"SELECT {FAQ_COLUMNS} FROM faq WHERE id = ?", (faq_id,)
        ).fetchone()
        if row is None:
            return None
        return _faq_from_row(row, self.variants(faq_id))

    def variants(self, faq_id: int) -> list[str]:
        """Return the alternative phrasings of one FAQ."""
        rows = self.conn.execute(
            "SELECT text FROM faq_variant WHERE faq_id = ? ORDER BY id", (faq_id,)
        ).fetchall()
        return [r["text"] for r in rows]

    def list(
        self,
        search: str | None = None,
        category: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Faq]:
        """Return FAQs filtered by free-text search and/or category."""
        sql = f"SELECT {FAQ_COLUMNS} FROM faq"
        clauses, params = self._filters(search, category)
        sql += clauses + " ORDER BY category, id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(sql, params).fetchall()
        if not rows:
            return []
        return self._with_variants(rows)

    def count(self, search: str | None = None, category: str | None = None) -> int:
        """Total FAQs matching the same filters as :meth:`list`."""
        sql = "SELECT COUNT(*) FROM faq"
        clauses, params = self._filters(search, category)
        return int(self.conn.execute(sql + clauses, params).fetchone()[0])

    def categories(self) -> list[dict[str, Any]]:
        """Return every category with its FAQ count, most populated first."""
        rows = self.conn.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM faq
            GROUP BY category
            ORDER BY count DESC, category
            """
        ).fetchall()
        return [{"category": r["category"], "count": r["count"]} for r in rows]

    def kb_entries(self) -> list[KbEntry]:
        """Return every indexable text unit: primary questions and variants."""
        entries: list[KbEntry] = []
        for row in self.conn.execute(f"SELECT {FAQ_COLUMNS} FROM faq ORDER BY id"):
            entries.append(KbEntry(faq_id=row["id"], text=row["question"], is_primary=True))
        for row in self.conn.execute(
            "SELECT faq_id, text FROM faq_variant ORDER BY faq_id, id"
        ):
            entries.append(
                KbEntry(faq_id=row["faq_id"], text=row["text"], is_primary=False)
            )
        return entries

    def questions(self, limit: int = 12) -> list[str]:
        """Return a sample of primary questions, used for suggestions."""
        rows = self.conn.execute(
            "SELECT question FROM faq ORDER BY RANDOM() LIMIT ?", (limit,)
        ).fetchall()
        return [r["question"] for r in rows]

    # ----------------------------------------------------------------- writes
    def create(
        self,
        question: str,
        answer: str,
        category: str,
        variants: Iterable[str] = (),
    ) -> int:
        """Insert a FAQ with its variants and return the new ID."""
        cur = self.conn.execute(
            "INSERT INTO faq (question, answer, category) VALUES (?, ?, ?)",
            (question.strip(), answer.strip(), (category or "عمومی").strip()),
        )
        faq_id = int(cur.lastrowid or 0)
        self._replace_variants(faq_id, variants)
        return faq_id

    def update(
        self,
        faq_id: int,
        question: str,
        answer: str,
        category: str,
        variants: Iterable[str] | None = None,
    ) -> bool:
        """Update a FAQ; variants are only touched when provided."""
        cur = self.conn.execute(
            """
            UPDATE faq
               SET question = ?, answer = ?, category = ?,
                   updated_at = datetime('now', 'localtime')
             WHERE id = ?
            """,
            (
                question.strip(),
                answer.strip(),
                (category or "عمومی").strip(),
                faq_id,
            ),
        )
        if cur.rowcount == 0:
            return False
        if variants is not None:
            self._replace_variants(faq_id, variants)
        return True

    def delete(self, faq_id: int) -> bool:
        """Delete a FAQ and its variants. Returns True when a row was removed."""
        cur = self.conn.execute("DELETE FROM faq WHERE id = ?", (faq_id,))
        return cur.rowcount > 0

    # ---------------------------------------------------------------- helpers
    def _replace_variants(self, faq_id: int, variants: Iterable[str]) -> None:
        """Rewrite the variant list of a FAQ, de-duplicated and trimmed."""
        self.conn.execute("DELETE FROM faq_variant WHERE faq_id = ?", (faq_id,))
        seen: set[str] = set()
        rows = []
        for text in variants or ():
            clean = " ".join(str(text).split())
            if not clean or clean in seen:
                continue
            seen.add(clean)
            rows.append((faq_id, clean))
        if rows:
            self.conn.executemany(
                "INSERT INTO faq_variant (faq_id, text) VALUES (?, ?)", rows
            )

    def _with_variants(self, rows: Sequence[sqlite3.Row]) -> list[Faq]:
        """Attach variants to a page of FAQ rows using a single extra query."""
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" for _ in ids)
        grouped: dict[int, list[str]] = {i: [] for i in ids}
        for row in self.conn.execute(
            f"SELECT faq_id, text FROM faq_variant WHERE faq_id IN ({placeholders}) "
            "ORDER BY id",
            ids,
        ):
            grouped.setdefault(row["faq_id"], []).append(row["text"])
        return [_faq_from_row(r, grouped.get(r["id"], [])) for r in rows]

    @staticmethod
    def _filters(search: str | None, category: str | None) -> tuple[str, list[Any]]:
        """Build the shared WHERE clause for list/count."""
        clauses: list[str] = []
        params: list[Any] = []
        if search:
            like = f"%{search.strip()}%"
            clauses.append(
                "(question LIKE ? OR answer LIKE ? OR category LIKE ? "
                "OR EXISTS (SELECT 1 FROM faq_variant v WHERE v.faq_id = faq.id "
                "AND v.text LIKE ?))"
            )
            params.extend([like, like, like, like])
        if category:
            clauses.append("category = ?")
            params.append(category.strip())
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


class ConversationRepository:
    """Conversation logging, history and feedback."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def log(
        self,
        session_id: str,
        user_text: str,
        matched_faq_id: int | None,
        matched_text: str | None,
        score: float,
        confidence: str,
        answered: bool,
        category: str | None,
        latency_ms: int,
    ) -> int:
        """Persist one chat turn and return its ID."""
        cur = self.conn.execute(
            """
            INSERT INTO conversation (
                session_id, user_text, matched_faq_id, matched_text, score,
                confidence, answered, category, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user_text,
                matched_faq_id,
                matched_text,
                float(score),
                confidence,
                1 if answered else 0,
                category,
                int(latency_ms),
            ),
        )
        return int(cur.lastrowid or 0)

    def get(self, conversation_id: int) -> ConversationTurn | None:
        """Return one logged turn."""
        row = self.conn.execute(
            "SELECT * FROM conversation WHERE id = ?", (conversation_id,)
        ).fetchone()
        return _turn_from_row(row) if row else None

    def by_session(self, session_id: str, limit: int = 100) -> list[ConversationTurn]:
        """Return the transcript of one session, oldest first."""
        rows = self.conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM conversation
                 WHERE session_id = ?
                 ORDER BY id DESC
                 LIMIT ?
            ) ORDER BY id ASC
            """,
            (session_id, limit),
        ).fetchall()
        return [_turn_from_row(r) for r in rows]

    def list(
        self,
        search: str | None = None,
        status: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationTurn]:
        """Return the conversation log, newest first.

        ``status`` accepts ``answered``, ``unanswered`` or ``None``.
        """
        sql, params = self._query(search, status, session_id)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [_turn_from_row(r) for r in self.conn.execute(sql, params)]

    def count(
        self,
        search: str | None = None,
        status: str | None = None,
        session_id: str | None = None,
    ) -> int:
        """Total logged turns matching the same filters as :meth:`list`."""
        sql, params = self._query(search, status, session_id)
        sql = "SELECT COUNT(*) FROM (" + sql + ")"
        return int(self.conn.execute(sql, params).fetchone()[0])

    def set_feedback(self, conversation_id: int, feedback: str | None) -> bool:
        """Store the visitor's rating of one answer."""
        cur = self.conn.execute(
            "UPDATE conversation SET feedback = ? WHERE id = ?",
            (feedback, conversation_id),
        )
        return cur.rowcount > 0

    def top_unanswered(self, limit: int = 8) -> list[dict[str, Any]]:
        """Group the questions the engine could not answer."""
        rows = self.conn.execute(
            """
            SELECT user_text AS message, COUNT(*) AS count,
                   ROUND(AVG(score), 3) AS avg_score
              FROM conversation
             WHERE answered = 0
             GROUP BY LOWER(TRIM(user_text))
             ORDER BY count DESC, message
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _query(
        search: str | None, status: str | None, session_id: str | None
    ) -> tuple[str, list[Any]]:
        """Build the shared SELECT for list/count."""
        sql = "SELECT * FROM conversation"
        clauses: list[str] = []
        params: list[Any] = []
        if search:
            like = f"%{search.strip()}%"
            clauses.append("(user_text LIKE ? OR matched_text LIKE ? OR session_id LIKE ?)")
            params.extend([like, like, like])
        if status == "answered":
            clauses.append("answered = 1")
        elif status == "unanswered":
            clauses.append("answered = 0")
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return sql, params


class HandoffRepository:
    """Human-agent handoff requests."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, session_id: str, reason: str | None, last_query: str | None) -> int:
        """Record a handoff request and return its ID (the ticket number)."""
        cur = self.conn.execute(
            "INSERT INTO handoff (session_id, reason, last_query) VALUES (?, ?, ?)",
            (session_id, (reason or "").strip() or None, (last_query or "").strip() or None),
        )
        return int(cur.lastrowid or 0)

    def list(self, limit: int = 50) -> list[HandoffRequest]:
        """Return recent handoff requests, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM handoff ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            HandoffRequest(
                id=r["id"],
                session_id=r["session_id"],
                reason=r["reason"],
                last_query=r["last_query"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def count(self) -> int:
        """Total handoff requests."""
        return int(self.conn.execute("SELECT COUNT(*) FROM handoff").fetchone()[0])


class AnalyticsRepository:
    """Aggregated metrics for the admin dashboard."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def overview(self, days: int = 14) -> dict[str, Any]:
        """Return every number the dashboard needs in one round trip."""
        totals = self.conn.execute(
            """
            SELECT COUNT(*)                                    AS turns,
                   COALESCE(SUM(answered), 0)                  AS answered,
                   COALESCE(AVG(score), 0)                     AS avg_score,
                   COALESCE(AVG(latency_ms), 0)                AS avg_latency,
                   COALESCE(SUM(feedback = 'up'), 0)           AS helpful,
                   COALESCE(SUM(feedback = 'down'), 0)         AS unhelpful
              FROM conversation
            """
        ).fetchone()

        turns = int(totals["turns"] or 0)
        answered = int(totals["answered"] or 0)

        confidence_rows = self.conn.execute(
            """
            SELECT confidence, COUNT(*) AS count
              FROM conversation
             GROUP BY confidence
            """
        ).fetchall()
        confidence = {r["confidence"]: r["count"] for r in confidence_rows}

        category_rows = self.conn.execute(
            """
            SELECT COALESCE(category, 'نامشخص') AS category, COUNT(*) AS count
              FROM conversation
             WHERE answered = 1
             GROUP BY category
             ORDER BY count DESC
             LIMIT 8
            """
        ).fetchall()

        daily_rows = self.conn.execute(
            """
            SELECT date(created_at) AS day,
                   COUNT(*)         AS total,
                   COALESCE(SUM(answered), 0) AS answered
              FROM conversation
             WHERE date(created_at) >= date('now', 'localtime', ?)
             GROUP BY day
            """,
            (f"-{max(days - 1, 0)} days",),
        ).fetchall()
        by_day = {r["day"]: r for r in daily_rows}
        series = []
        today = date.today()
        for offset in range(days - 1, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            row = by_day.get(day)
            series.append(
                {
                    "day": day,
                    "total": int(row["total"]) if row else 0,
                    "answered": int(row["answered"]) if row else 0,
                }
            )

        return {
            "turns": turns,
            "answered": answered,
            "unanswered": turns - answered,
            "match_rate": round(answered / turns * 100, 1) if turns else 0.0,
            "avg_score": round(float(totals["avg_score"] or 0), 3),
            "avg_latency_ms": round(float(totals["avg_latency"] or 0)),
            "helpful": int(totals["helpful"] or 0),
            "unhelpful": int(totals["unhelpful"] or 0),
            "confidence": {
                "high": confidence.get("high", 0),
                "medium": confidence.get("medium", 0),
                "low": confidence.get("low", 0),
            },
            "categories": [dict(r) for r in category_rows],
            "daily": series,
            "top_unanswered": ConversationRepository(self.conn).top_unanswered(),
            "handoffs": HandoffRepository(self.conn).count(),
        }
