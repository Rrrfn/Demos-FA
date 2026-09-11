# -*- coding: utf-8 -*-
"""ریپازیتوری هشدار — قواعد و رخدادها.

سه تضمین این لایه:

۱. **قاعدهٔ تکراری ساخته نمی‌شود.** یک ایندکس یکتا روی
   ``(مالک، دارایی، نوع، آستانه)`` جلوی ساخت قاعدهٔ موازی را می‌گیرد؛ نوشتن
   دوباره همان قاعده، قاعدهٔ موجود را برمی‌گرداند.
۲. **رخداد بی‌دلیل ثبت نمی‌شود.** هر وقوع در ``alert_events`` می‌نشیند و
   «مهارشده» بودنش هم ثبت می‌شود؛ بنابراین در پنل معلوم است که یک قاعده در
   بازهٔ خنک‌شدن چند بار تلاش کرده ولی آگاه‌سازی نشده.
۳. **دفتر رخداد کران‌دار است.** با عبور از سقف، قدیمی‌ترین‌ها حذف می‌شوند تا
   پایگاه داده در اجرای طولانی بی‌سقف رشد نکند.
"""
from __future__ import annotations

import time

from ..core.errors import RuleNotFound
from ..core.models import AlertEvent, AlertKind, AlertRule, AlertStatus

_RULE_COLUMNS = (
    "owner", "slug", "kind", "threshold", "status", "one_shot",
    "cooldown_seconds", "note", "created_at", "last_fired_at", "last_price",
    "fired_count",
)


def _row_to_rule(row) -> AlertRule:  # noqa: ANN001 - sqlite3.Row
    return AlertRule(
        id=int(row["id"]),
        slug=row["slug"],
        kind=AlertKind(row["kind"]),
        threshold=float(row["threshold"]),
        status=AlertStatus(row["status"]),
        one_shot=bool(row["one_shot"]),
        cooldown_seconds=int(row["cooldown_seconds"]),
        note=row["note"] or "",
        created_at=row["created_at"],
        last_fired_at=row["last_fired_at"],
        last_price=row["last_price"],
        fired_count=int(row["fired_count"] or 0),
        owner=row["owner"] or "",
    )


def _row_to_event(row) -> AlertEvent:  # noqa: ANN001 - sqlite3.Row
    return AlertEvent(
        id=int(row["id"]),
        rule_id=row["rule_id"],
        slug=row["slug"],
        kind=row["kind"],
        price=float(row["price"]),
        threshold=float(row["threshold"] or 0),
        message=row["message"],
        created_at=row["created_at"],
        suppressed=bool(row["suppressed"]),
        reason=row["reason"] or "",
        owner=row["owner"] or "",
    )


class AlertRepository:
    """خواندن و نوشتن قواعد هشدار و دفتر رخداد."""

    def __init__(self, storage) -> None:  # noqa: ANN001 - Storage
        self.storage = storage

    # ------------------------------------------------------------------ rules
    def add(
        self,
        slug: str,
        kind: AlertKind,
        threshold: float,
        *,
        owner: str = "",
        one_shot: bool = False,
        cooldown_seconds: int = 0,
        note: str = "",
    ) -> AlertRule:
        """ساخت قاعده؛ اگر همین قاعده باشد، همان برگردانده می‌شود."""
        now = time.time()
        with self.storage.transaction() as connection:
            connection.execute(
                "INSERT INTO alert_rules (owner, slug, kind, threshold, status, "
                "one_shot, cooldown_seconds, note, created_at, fired_count) "
                "VALUES (?,?,?,?,?,?,?,?,?,0) "
                "ON CONFLICT(owner, slug, kind, threshold) DO NOTHING",
                (
                    owner, slug, kind.value, float(threshold),
                    AlertStatus.ACTIVE.value, int(one_shot),
                    int(cooldown_seconds), note or "", now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM alert_rules WHERE owner = ? AND slug = ? AND kind = ? "
                "AND threshold = ?",
                (owner, slug, kind.value, float(threshold)),
            ).fetchone()
        return _row_to_rule(row)

    def get(self, rule_id: int) -> AlertRule | None:
        row = self.storage.query_one("SELECT * FROM alert_rules WHERE id = ?", (rule_id,))
        return _row_to_rule(row) if row else None

    def require(self, rule_id: int) -> AlertRule:
        """قاعده را برمی‌گرداند یا ``RuleNotFound`` می‌دهد."""
        rule = self.get(rule_id)
        if rule is None:
            raise RuleNotFound(rule_id)
        return rule

    def list(
        self,
        *,
        owner: str | None = None,
        slug: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AlertRule]:
        """فهرست قواعد با فیلتر و صفحه‌بندی."""
        clauses: list[str] = []
        params: list = []
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)
        if slug is not None:
            clauses.append("slug = ?")
            params.append(slug)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.storage.query(
            f"SELECT * FROM alert_rules {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, max(1, limit), max(0, offset)),
        )
        return [_row_to_rule(row) for row in rows]

    def count(self, *, owner: str | None = None) -> int:
        if owner is None:
            row = self.storage.query_one("SELECT COUNT(*) AS n FROM alert_rules")
        else:
            row = self.storage.query_one(
                "SELECT COUNT(*) AS n FROM alert_rules WHERE owner = ?", (owner,)
            )
        return int(row["n"]) if row else 0

    def active(self, *, limit: int = 1000) -> list[AlertRule]:
        """همهٔ قواعد فعال — ورودی موتور پایش."""
        rows = self.storage.query(
            "SELECT * FROM alert_rules WHERE status = 'active' ORDER BY id ASC LIMIT ?",
            (max(1, limit),),
        )
        return [_row_to_rule(row) for row in rows]

    def set_status(self, rule_id: int, status: AlertStatus) -> AlertRule:
        """فعال/متوقف کردن قاعده."""
        self.require(rule_id)
        self.storage.execute(
            "UPDATE alert_rules SET status = ? WHERE id = ?", (status.value, rule_id)
        )
        return self.require(rule_id)

    def delete(self, rule_id: int) -> bool:
        """حذف قاعده — رخدادهای ثبت‌شده دست‌نخورده می‌مانند (تاریخچه حفظ می‌شود)."""
        row = self.storage.query_one("SELECT id FROM alert_rules WHERE id = ?", (rule_id,))
        if row is None:
            return False
        self.storage.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
        return True

    def delete_by_slug(self, slug: str, *, owner: str | None = None) -> int:
        """حذف همهٔ قواعد یک دارایی (برای اقلام بازنشسته)."""
        if owner is None:
            row = self.storage.query_one("SELECT COUNT(*) AS n FROM alert_rules WHERE slug = ?", (slug,))
            self.storage.execute("DELETE FROM alert_rules WHERE slug = ?", (slug,))
        else:
            row = self.storage.query_one(
                "SELECT COUNT(*) AS n FROM alert_rules WHERE slug = ? AND owner = ?", (slug, owner)
            )
            self.storage.execute(
                "DELETE FROM alert_rules WHERE slug = ? AND owner = ?", (slug, owner)
            )
        return int(row["n"]) if row else 0

    def mark_fired(self, rule_id: int, price: float, at: float | None = None) -> None:
        """ثبت یک وقوع موفق روی قاعده."""
        stamp = at if at is not None else time.time()
        self.storage.execute(
            "UPDATE alert_rules SET last_fired_at = ?, last_price = ?, "
            "fired_count = fired_count + 1 WHERE id = ?",
            (stamp, price, rule_id),
        )

    def mark_checked(self, rule_id: int, price: float) -> None:
        """ثبت آخرین قیمت دیده‌شده، بدون شمردن وقوع."""
        self.storage.execute(
            "UPDATE alert_rules SET last_price = ? WHERE id = ?", (price, rule_id)
        )

    # ----------------------------------------------------------------- events
    def log_event(
        self,
        *,
        slug: str,
        kind: str,
        price: float,
        threshold: float,
        message: str,
        rule_id: int | None = None,
        owner: str = "",
        suppressed: bool = False,
        reason: str = "",
        at: float | None = None,
    ) -> AlertEvent:
        """ثبت رخداد (وقوع یا مهارشدن)."""
        stamp = at if at is not None else time.time()
        with self.storage.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO alert_events (rule_id, slug, kind, price, threshold, "
                "message, created_at, suppressed, reason, owner) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    rule_id, slug, kind, float(price), float(threshold or 0),
                    message, stamp, int(suppressed), reason or "", owner,
                ),
            )
            event_id = cursor.lastrowid
            row = connection.execute(
                "SELECT * FROM alert_events WHERE id = ?", (event_id,)
            ).fetchone()
        return _row_to_event(row)

    def events(
        self,
        *,
        slug: str | None = None,
        owner: str | None = None,
        include_suppressed: bool = True,
        since: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEvent]:
        """دفتر رخداد، تازه‌ترین‌ها اول."""
        clauses: list[str] = []
        params: list = []
        if slug is not None:
            clauses.append("slug = ?")
            params.append(slug)
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)
        if not include_suppressed:
            clauses.append("suppressed = 0")
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.storage.query(
            f"SELECT * FROM alert_events {where} ORDER BY created_at DESC, id DESC "
            "LIMIT ? OFFSET ?",
            (*params, max(1, limit), max(0, offset)),
        )
        return [_row_to_event(row) for row in rows]

    def events_count(self, *, since: float | None = None, owner: str | None = None) -> int:
        clauses: list[str] = []
        params: list = []
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = self.storage.query_one(
            f"SELECT COUNT(*) AS n FROM alert_events {where}", tuple(params)
        )
        return int(row["n"]) if row else 0

    def last_event_for(self, rule_id: int) -> AlertEvent | None:
        """آخرین رخداد یک قاعده — برای بررسی بازهٔ خنک‌شدن."""
        row = self.storage.query_one(
            "SELECT * FROM alert_events WHERE rule_id = ? ORDER BY created_at DESC LIMIT 1",
            (rule_id,),
        )
        return _row_to_event(row) if row else None

    def prune_events(self, max_events: int) -> int:
        """نگه‌داشتن فقط ``max_events`` رخداد تازه."""
        if max_events <= 0:
            return 0
        row = self.storage.query_one("SELECT COUNT(*) AS n FROM alert_events")
        total = int(row["n"]) if row else 0
        excess = total - max_events
        if excess <= 0:
            return 0
        self.storage.execute(
            "DELETE FROM alert_events WHERE id IN ("
            "  SELECT id FROM alert_events ORDER BY created_at ASC, id ASC LIMIT ?"
            ")",
            (excess,),
        )
        return excess

    def stats(self) -> dict:
        """آمار برای داشبورد."""
        now = time.time()
        day_ago = now - 86400
        rules = self.storage.query_one(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active "
            "FROM alert_rules"
        )
        return {
            "rules": int(rules["n"]) if rules else 0,
            "active_rules": int(rules["active"] or 0) if rules else 0,
            "events_24h": self.events_count(since=day_ago),
            "events_total": self.events_count(),
        }


__all__ = ["AlertRepository"]
