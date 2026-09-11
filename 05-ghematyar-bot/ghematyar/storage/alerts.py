# -*- coding: utf-8 -*-
"""انبار دادهٔ هشدارها و رویدادهای آن‌ها.

سه تضمین مهم در همین لایه اعمال می‌شود، نه در هندلرها:

* **بدون تکرار**: ایندکس یکتای ``uniq_alerts_signature`` اجازه نمی‌دهد
  کاربر برای یک قلم، یک جهت و یک عدد، دو هشدار زندهٔ هم‌زمان بسازد.
* **سقف تعداد**: تعداد هشدارهای زندهٔ کاربر پیش از درج شمرده می‌شود.
* **گزارش‌پذیری**: هر رخداد (ساخت، اعلان، سرکوب، خطا) در ``alert_events``
  ثبت می‌شود؛ محدودیت نرخ و فاصلهٔ اعلان از همین‌جا محاسبه می‌شود.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from enum import Enum

from ..core.errors import AlertLimitReached, AlertNotFound, DuplicateAlert
from .database import Database


class AlertStatus(str, Enum):
    """وضعیت چرخهٔ عمر یک هشدار."""

    ACTIVE = "active"        # در حال پایش
    PAUSED = "paused"        # موقتاً خاموش توسط کاربر
    TRIGGERED = "triggered"  # یک‌بار مصرف، فعال شده
    DISABLED = "disabled"    # به‌دلیل خطای مکرر ارسال کنار گذاشته شده

    @property
    def label(self) -> str:
        return {
            "active": "فعال",
            "paused": "موقتاً خاموش",
            "triggered": "اجرا شده",
            "disabled": "غیرفعال",
        }[self.value]

    @property
    def is_watchable(self) -> bool:
        return self is AlertStatus.ACTIVE


class AlertDirection(str, Enum):
    """جهت شرط."""

    ABOVE = "above"
    BELOW = "below"

    @property
    def label(self) -> str:
        return "بالای" if self is AlertDirection.ABOVE else "زیر"

    def matches(self, price: float, target: float) -> bool:
        if self is AlertDirection.ABOVE:
            return price >= target
        return price <= target


# وضعیت‌هایی که در سقف تعداد و یکتایی حساب می‌شوند
_LIVE_STATUSES = (AlertStatus.ACTIVE.value, AlertStatus.PAUSED.value,
                  AlertStatus.TRIGGERED.value)


@dataclass(slots=True)
class Alert:
    """یک هشدار قیمت."""

    id: int
    user_id: int
    slug: str
    direction: AlertDirection
    target: float
    status: AlertStatus
    one_shot: bool
    cooldown_seconds: int
    last_notified_at: float | None
    triggered_count: int
    failure_count: int
    last_price: float | None
    last_checked_at: float | None
    created_at: float
    updated_at: float

    @property
    def watchable(self) -> bool:
        """آیا این هشدار باید در دور بعدی پایش بررسی شود؟"""
        return self.status is AlertStatus.ACTIVE

    def matches(self, price: float) -> bool:
        """آیا شرط هشدار با این قیمت برقرار است؟"""
        return self.direction.matches(price, self.target)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Alert":
        return cls(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            slug=str(row["slug"]),
            direction=AlertDirection(row["direction"]),
            target=float(row["target"]),
            status=AlertStatus(row["status"]),
            one_shot=bool(row["one_shot"]),
            cooldown_seconds=int(row["cooldown_seconds"]),
            last_notified_at=row["last_notified_at"],
            triggered_count=int(row["triggered_count"]),
            failure_count=int(row["failure_count"]),
            last_price=row["last_price"],
            last_checked_at=row["last_checked_at"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )


class AlertRepository:
    """دسترسی به جدول هشدارها."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ read
    def get(self, alert_id: int, user_id: int | None = None) -> Alert | None:
        sql = "SELECT * FROM alerts WHERE id = ?"
        params: list[object] = [alert_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        row = self.db.connection.execute(sql, params).fetchone()
        return Alert.from_row(row) if row else None

    def list_for_user(
        self,
        user_id: int,
        *,
        statuses: tuple[AlertStatus, ...] | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        sql = "SELECT * FROM alerts WHERE user_id = ?"
        params: list[object] = [user_id]
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend(s.value for s in statuses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self.db.connection.execute(sql, params).fetchall()
        return [Alert.from_row(r) for r in rows]

    def list_watchable(self, slugs: list[str] | None = None) -> list[Alert]:
        """هشدارهای فعال که باید پایش شوند (مبنای حلقهٔ پس‌زمینه)."""
        sql = "SELECT * FROM alerts WHERE status = ?"
        params: list[object] = [AlertStatus.ACTIVE.value]
        if slugs:
            placeholders = ",".join("?" for _ in slugs)
            sql += f" AND slug IN ({placeholders})"
            params.extend(slugs)
        sql += " ORDER BY id"
        rows = self.db.connection.execute(sql, params).fetchall()
        return [Alert.from_row(r) for r in rows]

    def count_live(self, user_id: int) -> int:
        placeholders = ",".join("?" for _ in _LIVE_STATUSES)
        row = self.db.connection.execute(
            f"SELECT COUNT(*) AS n FROM alerts WHERE user_id = ? AND status IN ({placeholders})",
            (user_id, *_LIVE_STATUSES),
        ).fetchone()
        return int(row["n"])

    def find_duplicate(
        self, user_id: int, slug: str, direction: AlertDirection, target: float
    ) -> Alert | None:
        """هشدار زندهٔ یکسان (برای پیام راهنما، پیش از برخورد با ایندکس)."""
        placeholders = ",".join("?" for _ in _LIVE_STATUSES)
        row = self.db.connection.execute(
            f"""SELECT * FROM alerts
                WHERE user_id = ? AND slug = ? AND direction = ? AND target = ?
                  AND status IN ({placeholders})""",
            (user_id, slug, direction.value, target, *_LIVE_STATUSES),
        ).fetchone()
        return Alert.from_row(row) if row else None

    # ----------------------------------------------------------------- write
    def create(
        self,
        user_id: int,
        slug: str,
        direction: AlertDirection,
        target: float,
        *,
        one_shot: bool = True,
        cooldown_seconds: int = 0,
        limit: int = 15,
    ) -> Alert:
        """ساخت هشدار جدید.

        در صورت تکرار، سقف تعداد یا مقدار نامعتبر، خطای دامنه می‌دهد.
        """
        now = time.time()
        with self.db.transaction() as conn:
            existing = self.find_duplicate(user_id, slug, direction, target)
            if existing is not None:
                raise DuplicateAlert(existing.id)
            placeholders = ",".join("?" for _ in _LIVE_STATUSES)
            count = conn.execute(
                f"SELECT COUNT(*) AS n FROM alerts WHERE user_id = ? AND status IN ({placeholders})",
                (user_id, *_LIVE_STATUSES),
            ).fetchone()["n"]
            if int(count) >= limit:
                raise AlertLimitReached(limit)
            cursor = conn.execute(
                """INSERT INTO alerts
                       (user_id, slug, direction, target, status, one_shot,
                        cooldown_seconds, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (user_id, slug, direction.value, float(target), AlertStatus.ACTIVE.value,
                 int(one_shot), int(cooldown_seconds), now, now),
            )
            alert_id = int(cursor.lastrowid or 0)
        created = self.get(alert_id, user_id)
        assert created is not None
        return created

    def update(
        self,
        alert_id: int,
        user_id: int,
        *,
        target: float | None = None,
        direction: AlertDirection | None = None,
        one_shot: bool | None = None,
    ) -> Alert:
        """ویرایش شرط یک هشدار."""
        alert = self.get(alert_id, user_id)
        if alert is None:
            raise AlertNotFound(alert_id)
        fields: list[str] = []
        params: list[object] = []
        if target is not None:
            fields.append("target = ?")
            params.append(float(target))
        if direction is not None:
            fields.append("direction = ?")
            params.append(direction.value)
        if one_shot is not None:
            fields.append("one_shot = ?")
            params.append(int(one_shot))
        if not fields:
            return alert
        fields.append("updated_at = ?")
        params.append(time.time())
        params.extend([alert_id, user_id])
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE alerts SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                params,
            )
        updated = self.get(alert_id, user_id)
        assert updated is not None
        return updated

    def set_status(self, alert_id: int, user_id: int, status: AlertStatus) -> bool:
        """تغییر وضعیت هشدار (خاموش/روشن/غیرفعال)."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE alerts SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (status.value, time.time(), alert_id, user_id),
            )
            return cursor.rowcount > 0

    def toggle_paused(self, alert_id: int, user_id: int) -> Alert | None:
        """خاموش/روشن کردن هشدار فعال یا خاموش‌شده."""
        alert = self.get(alert_id, user_id)
        if alert is None:
            return None
        if alert.status is AlertStatus.ACTIVE:
            self.set_status(alert_id, user_id, AlertStatus.PAUSED)
        elif alert.status is AlertStatus.PAUSED:
            self.set_status(alert_id, user_id, AlertStatus.ACTIVE)
        return self.get(alert_id, user_id)

    def delete(self, alert_id: int, user_id: int) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM alerts WHERE id = ? AND user_id = ?", (alert_id, user_id)
            )
            return cursor.rowcount > 0

    def delete_all(self, user_id: int) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM alerts WHERE user_id = ?", (user_id,))
            return cursor.rowcount

    # ------------------------------------------------------------ monitoring
    def mark_evaluated(self, alert_id: int, price: float) -> None:
        """ثبت اینکه این هشدار در این دور با این قیمت بررسی شد."""
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE alerts SET last_price = ?, last_checked_at = ? WHERE id = ?",
                (float(price), time.time(), alert_id),
            )

    def mark_notified(self, alert_id: int, price: float, *, one_shot: bool) -> None:
        """ثبت اعلان موفق؛ در حالت یک‌بار مصرف وضعیت به executed می‌رود."""
        now = time.time()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE alerts
                   SET last_notified_at = ?, triggered_count = triggered_count + 1,
                       last_price = ?, failure_count = 0,
                       status = ?, updated_at = ?
                   WHERE id = ?""",
                (now, float(price),
                 AlertStatus.TRIGGERED.value if one_shot else AlertStatus.ACTIVE.value,
                 now, alert_id),
            )

    def mark_failed(self, alert_id: int, *, disable_after: int) -> AlertStatus | None:
        """ثبت خطای ارسال؛ پس از تکرار، هشدار غیرفعال می‌شود.

        این حالت وقتی رخ می‌دهد که کاربر ربات را بلاک کرده باشد؛ ادامهٔ
        تلاش بی‌فایده است و منابع را مصرف می‌کند.
        """
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE alerts SET failure_count = failure_count + 1, updated_at = ? WHERE id = ?",
                (time.time(), alert_id),
            )
            row = conn.execute(
                "SELECT failure_count FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if row and int(row["failure_count"]) >= disable_after:
                conn.execute(
                    "UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?",
                    (AlertStatus.DISABLED.value, time.time(), alert_id),
                )
                return AlertStatus.DISABLED
        return None


class AlertEventRepository:
    """گزارش رخدادهای هشدار — مبنای محدودیت نرخ و شفافیت."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        user_id: int,
        slug: str,
        kind: str,
        *,
        alert_id: int | None = None,
        price: float | None = None,
        target: float | None = None,
        detail: str = "",
    ) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO alert_events
                       (alert_id, user_id, slug, kind, price, target, detail, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (alert_id, user_id, slug, kind, price, target, detail[:500], time.time()),
            )
            return int(cursor.lastrowid or 0)

    def count_since(self, user_id: int, since: float, kinds: tuple[str, ...] = ("triggered",)) -> int:
        placeholders = ",".join("?" for _ in kinds)
        row = self.db.connection.execute(
            f"""SELECT COUNT(*) AS n FROM alert_events
                WHERE user_id = ? AND created_at >= ? AND kind IN ({placeholders})""",
            (user_id, since, *kinds),
        ).fetchone()
        return int(row["n"])

    def last_time(
        self, user_id: int, slug: str, kinds: tuple[str, ...] = ("triggered",)
    ) -> float | None:
        placeholders = ",".join("?" for _ in kinds)
        row = self.db.connection.execute(
            f"""SELECT MAX(created_at) AS t FROM alert_events
                WHERE user_id = ? AND slug = ? AND kind IN ({placeholders})""",
            (user_id, slug, *kinds),
        ).fetchone()
        return float(row["t"]) if row and row["t"] is not None else None

    def list_recent(self, user_id: int, limit: int = 20) -> list[sqlite3.Row]:
        return self.db.connection.execute(
            """SELECT * FROM alert_events WHERE user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()

    def prune(self, older_than_days: int = 30) -> int:
        """حذف رویدادهای قدیمی برای کوچک نگه‌داشتن پایگاه داده."""
        cutoff = time.time() - older_than_days * 86400
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM alert_events WHERE created_at < ?", (cutoff,))
            return cursor.rowcount
