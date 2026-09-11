# -*- coding: utf-8 -*-
"""تست پایگاه داده و انبارهای داده."""
from __future__ import annotations

import time

import pytest

from ghematyar.core.models import Quote
from ghematyar.storage import AlertDirection, AlertStatus, Storage, open_storage
from ghematyar.storage.database import SCHEMA_VERSION


class TestSchema:
    """ساخت و مهاجرت اسکیما."""

    def test_migration_sets_version(self, storage: Storage):
        row = storage.database.connection.execute("PRAGMA user_version").fetchone()
        assert int(row[0]) == SCHEMA_VERSION

    def test_migration_is_idempotent(self, storage: Storage):
        """اجرای دوباره نباید خطا بدهد و داده را از دست بدهد."""
        storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        assert storage.database.migrate() == SCHEMA_VERSION
        assert storage.alerts.count_live(1) == 1

    def test_wal_mode_enabled(self, storage: Storage):
        row = storage.database.connection.execute("PRAGMA journal_mode").fetchone()
        assert str(row[0]).lower() == "wal"

    def test_reopen_existing_database(self, config):
        """باز کردن دوبارهٔ همان فایل، دادهٔ موجود را حفظ می‌کند."""
        first = open_storage(config.db_path)
        first.alerts.create(1, "usd", AlertDirection.ABOVE, 123.0)
        first.close()

        second = open_storage(config.db_path)
        assert second.alerts.count_live(1) == 1
        second.close()

    def test_all_tables_exist(self, storage: Storage):
        rows = storage.database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {str(r["name"]) for r in rows}
        assert {"alerts", "alert_events", "price_history", "watchlist", "users"} <= names


class TestAlertRepository:
    """CRUD و سیاست‌های هشدار در لایهٔ داده."""

    def test_create_and_read(self, storage: Storage):
        alert = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 250_000.0)
        assert alert.id > 0
        assert alert.status is AlertStatus.ACTIVE
        assert alert.one_shot is True
        assert storage.alerts.get(alert.id, 1) is not None

    def test_duplicate_is_rejected(self, storage: Storage):
        from ghematyar.core.errors import DuplicateAlert

        first = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 250_000.0)
        with pytest.raises(DuplicateAlert) as exc:
            storage.alerts.create(1, "usd", AlertDirection.ABOVE, 250_000.0)
        assert exc.value.alert_id == first.id

    def test_duplicate_check_ignores_deleted(self, storage: Storage):
        """پس از حذف، همان هشدار را می‌توان دوباره ساخت."""
        first = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 250_000.0)
        storage.alerts.delete(first.id, 1)
        again = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 250_000.0)
        assert again.id != first.id

    def test_different_direction_is_not_duplicate(self, storage: Storage):
        storage.alerts.create(1, "usd", AlertDirection.ABOVE, 250_000.0)
        other = storage.alerts.create(1, "usd", AlertDirection.BELOW, 250_000.0)
        assert other.id > 0

    def test_limit_is_enforced(self, storage: Storage):
        from ghematyar.core.errors import AlertLimitReached

        for index in range(3):
            storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0 + index, limit=3)
        with pytest.raises(AlertLimitReached):
            storage.alerts.create(1, "usd", AlertDirection.ABOVE, 999.0, limit=3)

    def test_users_are_isolated(self, storage: Storage):
        storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        storage.alerts.create(2, "usd", AlertDirection.ABOVE, 100.0)
        assert storage.alerts.count_live(1) == 1
        assert storage.alerts.count_live(2) == 1
        assert len(storage.alerts.list_for_user(1)) == 1

    def test_get_requires_owner(self, storage: Storage):
        alert = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        assert storage.alerts.get(alert.id, 2) is None

    def test_toggle_paused_and_back(self, storage: Storage):
        alert = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        paused = storage.alerts.toggle_paused(alert.id, 1)
        assert paused is not None and paused.status is AlertStatus.PAUSED
        resumed = storage.alerts.toggle_paused(alert.id, 1)
        assert resumed is not None and resumed.status is AlertStatus.ACTIVE

    def test_watchable_excludes_inactive(self, storage: Storage):
        first = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        storage.alerts.create(1, "eur", AlertDirection.ABOVE, 200.0)
        storage.alerts.set_status(first.id, 1, AlertStatus.PAUSED)
        watchable = storage.alerts.list_watchable()
        assert [a.slug for a in watchable] == ["eur"]

    def test_watchable_filter_by_slug(self, storage: Storage):
        storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        storage.alerts.create(1, "eur", AlertDirection.ABOVE, 200.0)
        assert [a.slug for a in storage.alerts.list_watchable(["eur"])] == ["eur"]

    def test_mark_notified_one_shot_disables(self, storage: Storage):
        alert = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0, one_shot=True)
        storage.alerts.mark_notified(alert.id, 150.0, one_shot=True)
        updated = storage.alerts.get(alert.id, 1)
        assert updated is not None
        assert updated.status is AlertStatus.TRIGGERED
        assert updated.triggered_count == 1
        assert updated.last_price == 150.0

    def test_mark_notified_recurring_stays_active(self, storage: Storage):
        alert = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0, one_shot=False)
        storage.alerts.mark_notified(alert.id, 150.0, one_shot=False)
        updated = storage.alerts.get(alert.id, 1)
        assert updated is not None and updated.status is AlertStatus.ACTIVE

    def test_failures_disable_after_threshold(self, storage: Storage):
        alert = storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        assert storage.alerts.mark_failed(alert.id, disable_after=2) is None
        assert storage.alerts.mark_failed(alert.id, disable_after=2) is AlertStatus.DISABLED
        updated = storage.alerts.get(alert.id, 1)
        assert updated is not None and updated.status is AlertStatus.DISABLED

    def test_delete_all(self, storage: Storage):
        storage.alerts.create(1, "usd", AlertDirection.ABOVE, 100.0)
        storage.alerts.create(1, "eur", AlertDirection.ABOVE, 100.0)
        assert storage.alerts.delete_all(1) == 2
        assert storage.alerts.count_live(1) == 0


class TestAlertEvents:
    """گزارش رویدادها و محاسبهٔ محدودیت نرخ."""

    def test_add_and_count(self, storage: Storage):
        storage.events.add(1, "usd", "triggered", price=100.0)
        storage.events.add(1, "usd", "triggered", price=101.0)
        assert storage.events.count_since(1, time.time() - 60) == 2

    def test_count_is_per_user_and_kind(self, storage: Storage):
        storage.events.add(1, "usd", "triggered")
        storage.events.add(2, "usd", "triggered")
        storage.events.add(1, "usd", "suppressed")
        assert storage.events.count_since(1, time.time() - 60) == 1
        assert storage.events.count_since(1, time.time() - 60, ("suppressed",)) == 1

    def test_old_events_excluded(self, storage: Storage):
        storage.events.add(1, "usd", "triggered")
        future = time.time() + 7200
        assert storage.events.count_since(1, future) == 0

    def test_last_time_for_slug(self, storage: Storage):
        assert storage.events.last_time(1, "usd") is None
        storage.events.add(1, "usd", "triggered")
        assert storage.events.last_time(1, "usd") is not None

    def test_prune_removes_old(self, storage: Storage):
        with storage.database.transaction() as conn:
            conn.execute(
                "INSERT INTO alert_events (user_id, slug, kind, detail, created_at) "
                "VALUES (?,?,?,?,?)",
                (1, "usd", "triggered", "", time.time() - 40 * 86400),
            )
        assert storage.events.prune(30) == 1


class TestHistory:
    """ثبت و خواندن تاریخچهٔ قیمت."""

    @staticmethod
    def _quote(slug: str = "usd", price: float = 100.0, *, age: float = 0.0) -> Quote:
        now = time.time()
        return Quote(slug=slug, price=price, source="test", observed_at=now - age,
                     fetched_at=now - age)

    def test_record_and_latest(self, storage: Storage):
        storage.history.record(self._quote(price=250.0))
        latest = storage.history.latest("usd")
        assert latest is not None and latest.price == 250.0

    def test_sampling_skips_recent_duplicates(self, storage: Storage):
        """دو ثبت پشت‌سرهم در یک دقیقه نباید دو رکورد بسازد."""
        written = storage.history.record_many({"usd": self._quote(price=100.0)})
        again = storage.history.record_many({"usd": self._quote(price=101.0)})
        assert written == 1
        assert again == 0

    def test_sampling_allows_after_gap(self, storage: Storage):
        storage.history.record(self._quote(price=100.0, age=3600))
        written = storage.history.record_many({"usd": self._quote(price=101.0)})
        assert written == 1

    def test_change_since_window(self, storage: Storage):
        """تغییر باید نسبت به مشاهدهٔ واقعیِ گذشته حساب شود."""
        storage.history.record(self._quote(price=100.0, age=90000))
        result = storage.history.change_since("usd", 110.0, 86400)
        assert result is not None
        delta, pct, label = result
        assert delta == pytest.approx(10.0)
        assert pct == pytest.approx(10.0)
        assert "۲۴" in label

    def test_change_requires_history(self, storage: Storage):
        """بدون تاریخچه، هیچ عددی ساخته نمی‌شود."""
        assert storage.history.change_since("usd", 110.0, 86400) is None

    def test_price_at_or_before(self, storage: Storage):
        storage.history.record(self._quote(price=50.0, age=7200))
        point = storage.history.price_at_or_before("usd", time.time() - 3600)
        assert point is not None and point.price == 50.0

    def test_series_orders_by_time(self, storage: Storage):
        storage.history.record(self._quote(price=10.0, age=300))
        storage.history.record(self._quote(price=20.0, age=120))
        series = storage.history.series("usd", hours=24)
        assert [p.price for p in series] == [10.0, 20.0]

    def test_stats(self, storage: Storage):
        storage.history.record(self._quote(slug="usd"))
        storage.history.record(self._quote(slug="eur"))
        assert storage.history.stats() == {"points": 2, "assets": 2}

    def test_coverage(self, storage: Storage):
        storage.history.record(self._quote(price=10.0, age=600))
        first, last, count = storage.history.coverage("usd")
        assert count == 1 and first == last

    def test_prune(self, storage: Storage):
        with storage.database.transaction() as conn:
            conn.execute(
                "INSERT INTO price_history (slug, price, unit, source, observed_at, captured_at)"
                " VALUES (?,?,?,?,?,?)",
                ("usd", 1.0, "toman", "test", time.time() - 100 * 86400,
                 time.time() - 100 * 86400),
            )
        assert storage.history.prune(90) == 1


class TestWatchlistAndUsers:
    """دیده‌بان و ثبت کاربر."""

    def test_add_and_list(self, storage: Storage):
        assert storage.watchlist.add(1, "bitcoin") is True
        assert storage.watchlist.list_for_user(1) == ["bitcoin"]

    def test_duplicate_add_returns_false(self, storage: Storage):
        storage.watchlist.add(1, "bitcoin")
        assert storage.watchlist.add(1, "bitcoin") is False

    def test_limit_is_enforced(self, storage: Storage):
        for index in range(storage.watchlist.limit):
            assert storage.watchlist.add(1, f"asset{index}") is True
        assert storage.watchlist.add(1, "one-too-many") is False

    def test_toggle(self, storage: Storage):
        assert storage.watchlist.toggle(1, "usd") is True
        assert storage.watchlist.toggle(1, "usd") is False
        assert storage.watchlist.list_for_user(1) == []

    def test_remove_and_clear(self, storage: Storage):
        storage.watchlist.add(1, "usd")
        storage.watchlist.add(1, "eur")
        assert storage.watchlist.remove(1, "usd") is True
        assert storage.watchlist.clear(1) == 1

    def test_user_touch_is_idempotent(self, storage: Storage):
        storage.users.touch(5, chat_id=5)
        storage.users.touch(5, chat_id=5)
        assert storage.users.count() == 1

    def test_notifications_default_enabled(self, storage: Storage):
        assert storage.users.notifications_enabled(999) is True
        storage.users.touch(999)
        storage.users.set_notifications(999, False)
        assert storage.users.notifications_enabled(999) is False
