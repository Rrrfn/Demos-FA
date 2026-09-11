# -*- coding: utf-8 -*-
"""تست هندلرها از راه dispatcher واقعی.

آپدیت‌ها با ``feed_update`` به همان Dispatcher تولیدی می‌روند و پاسخ‌ها از
نشست قلابی خوانده می‌شوند. یعنی مسیر کامل «آپدیت → فیلتر → هندلر → ارسال»
آزموده می‌شود، نه فقط توابع.
"""
from __future__ import annotations

import pytest

from ghematyar.bot import build_dispatcher
from ghematyar.core.models import Quote
from ghematyar.services import AlertService, MarketService, Services
from ghematyar.storage import AlertDirection, Storage
from tests.fakes import FakeSession, make_bot, make_callback_update, make_message_update


def quote(slug: str = "usd", price: float = 250_000.0, *, change_pct: float | None = 1.5) -> Quote:
    import time

    now = time.time()
    item = Quote(slug=slug, price=price, source="tgju", observed_at=now, fetched_at=now)
    if change_pct is not None:
        item.change_pct = change_pct
        item.change_abs = price * change_pct / 100
        item.change_basis = "نسبت به ۲۴ ساعت پیش"
    return item


@pytest.fixture()
def wired(config, storage, session):
    """(dispatcher, session, services) با منبع دادهٔ تزریق‌شده."""
    def _build(provider_quotes: dict[str, Quote]):
        from tests.fakes import ScriptedProvider

        provider = ScriptedProvider("tgju", provider_quotes, config.data)
        market = MarketService(config, storage, providers={"tgju": provider})
        alerts = AlertService(config, storage.alerts, storage.events, storage.users)
        services = Services(config=config, storage=storage, market=market, alerts=alerts)
        bot = make_bot(session)
        dispatcher = build_dispatcher(config, services)
        return dispatcher, bot, services

    return _build


class TestRouting:
    """سیم‌کشی dispatcher."""

    def test_routers_are_registered(self, config, storage):
        """همهٔ routerها وصل شده‌اند و هندلرها واقعاً ثبت شده‌اند."""
        from ghematyar.bot.handlers import BUILDERS
        from ghematyar.services import AlertService, MarketService, Services

        market = MarketService(config, storage, providers={})
        alerts = AlertService(config, storage.alerts, storage.events, storage.users)
        services = Services(config=config, storage=storage, market=market, alerts=alerts)
        dispatcher = build_dispatcher(config, services)

        assert len(dispatcher.sub_routers) == len(BUILDERS)
        registered = sum(
            len(router.message.handlers) + len(router.callback_query.handlers)
            for router in dispatcher.sub_routers
        )
        assert registered > 20
        assert "services" in dispatcher.workflow_data
        assert "config" in dispatcher.workflow_data

    def test_dispatcher_can_be_built_repeatedly(self, config, storage):
        """ساخت دوبارهٔ برنامه در یک پروسه نباید خطا بدهد."""
        from ghematyar.services import AlertService, MarketService, Services

        market = MarketService(config, storage, providers={})
        alerts = AlertService(config, storage.alerts, storage.events, storage.users)
        services = Services(config=config, storage=storage, market=market, alerts=alerts)
        first = build_dispatcher(config, services)
        second = build_dispatcher(config, services)
        assert first is not second
        assert len(second.sub_routers) == len(first.sub_routers)

    def test_routers_are_not_shared_between_dispatchers(self, config, storage):
        """هر Dispatcher باید routerهای مستقل داشته باشد."""
        from ghematyar.services import AlertService, MarketService, Services

        market = MarketService(config, storage, providers={})
        alerts = AlertService(config, storage.alerts, storage.events, storage.users)
        services = Services(config=config, storage=storage, market=market, alerts=alerts)
        first = build_dispatcher(config, services)
        second = build_dispatcher(config, services)
        first_ids = {id(router) for router in first.sub_routers}
        second_ids = {id(router) for router in second.sub_routers}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.anyio
    async def test_start_command_responds(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("/start"))
        assert any("قیمت‌یار" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_help_command_lists_commands(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("/help"))
        assert any("/market" in text and "/alert" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_unknown_command_falls_back_gracefully(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("/nonsense"))
        assert session.sent_texts  # راهنما فرستاده می‌شود، نه سکوت


class TestMarketCommands:
    """دستورهای قیمت."""

    @pytest.mark.anyio
    async def test_market_overview(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote(), "bitcoin": quote("bitcoin", 78_000)})
        await dispatcher.feed_update(bot, make_message_update("/market"))
        assert any("نمای بازار" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_price_by_name(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote(price=235_975)})
        await dispatcher.feed_update(bot, make_message_update("/price دلار"))
        joined = "\n".join(session.sent_texts)
        assert "دلار آمریکا" in joined
        assert "منبع" in joined  # الزام: نمایش منبع

    @pytest.mark.anyio
    async def test_price_shows_change_and_time(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote(change_pct=2.5)})
        await dispatcher.feed_update(bot, make_message_update("/price دلار"))
        joined = "\n".join(session.sent_texts)
        assert "تغییر" in joined
        assert "آخرین داده" in joined

    @pytest.mark.anyio
    async def test_price_without_history_shows_dash(self, wired, session):
        """بدون تاریخچه، تغییر «—» است — نه عدد ساختگی."""
        dispatcher, bot, _ = wired({"usd": quote(change_pct=None)})
        await dispatcher.feed_update(bot, make_message_update("/price دلار"))
        joined = "\n".join(session.sent_texts)
        assert "—" in joined
        assert "تاریخچهٔ کافی" in joined

    @pytest.mark.anyio
    async def test_price_unknown_name(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("/price آبمیوه"))
        assert any("پیدا نکردم" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_unavailable_price_is_honest(self, config, storage, session):
        """قطع منبع → پیام «دردسترس نیست» بدون هیچ عددی."""
        from ghematyar.core.errors import ProviderError
        from ghematyar.services import AlertService, MarketService, Services
        from tests.fakes import ScriptedProvider

        provider = ScriptedProvider("tgju", ProviderError("tgju", "down"), config.data)
        market = MarketService(config, storage, providers={"tgju": provider})
        alerts = AlertService(config, storage.alerts, storage.events, storage.users)
        services = Services(config=config, storage=storage, market=market, alerts=alerts)
        bot = make_bot(session)
        dispatcher = build_dispatcher(config, services)

        await dispatcher.feed_update(bot, make_message_update("/price دلار"))
        joined = "\n".join(session.sent_texts)
        assert "در دسترس نیست" in joined
        assert "۲۳۵" not in joined  # هیچ قیمت ساختگی

    @pytest.mark.anyio
    async def test_category_command(self, wired, session):
        dispatcher, bot, _ = wired({"bitcoin": quote("bitcoin", 78_000)})
        await dispatcher.feed_update(bot, make_message_update("/crypto"))
        assert any("رمزارز" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_chart_without_history_is_honest(self, wired, session):
        dispatcher, bot, _ = wired({"bitcoin": quote("bitcoin", 78_000)})
        await dispatcher.feed_update(bot, make_message_update("/chart بیت‌کوین"))
        joined = "\n".join(session.sent_texts)
        assert "تاریخچهٔ کافی" in joined
        assert session.sent_captions == []  # عکسی ارسال نشود

    @pytest.mark.anyio
    async def test_free_text_price_query(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote(price=235_975)})
        await dispatcher.feed_update(bot, make_message_update("قیمت دلار چنده؟"))
        assert any("دلار آمریکا" in text for text in session.sent_texts)


class TestAlertCommands:
    """دستورهای هشدار."""

    @pytest.mark.anyio
    async def test_free_text_creates_alert(self, wired, session, storage):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("دلار بالای ۲۵۰۰۰۰"))
        assert any("هشدار ثبت شد" in text for text in session.sent_texts)
        alerts = storage.alerts.list_for_user(777)
        assert len(alerts) == 1
        assert alerts[0].slug == "usd"
        assert alerts[0].target == 250_000
        assert alerts[0].direction is AlertDirection.ABOVE

    @pytest.mark.anyio
    async def test_alert_command_with_argument(self, wired, session, storage):
        dispatcher, bot, _ = wired({"bitcoin": quote("bitcoin", 78_000)})
        await dispatcher.feed_update(bot, make_message_update("/alert بیت‌کوین بالای ۸۵۰۰۰"))
        assert len(storage.alerts.list_for_user(777)) == 1

    @pytest.mark.anyio
    async def test_duplicate_alert_is_explained(self, wired, session, storage):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("دلار بالای ۲۵۰۰۰۰"))
        session.clear()
        await dispatcher.feed_update(bot, make_message_update("دلار بالای ۲۵۰۰۰۰"))
        assert any("از قبل ثبت شده" in text for text in session.sent_texts)
        assert len(storage.alerts.list_for_user(777)) == 1

    @pytest.mark.anyio
    async def test_alert_limit_is_explained(self, wired, session, config):
        dispatcher, bot, _ = wired({"usd": quote()})
        for amount in (100_000, 200_000, 300_000):
            await dispatcher.feed_update(bot, make_message_update(f"دلار بالای {amount}"))
        session.clear()
        await dispatcher.feed_update(bot, make_message_update("دلار بالای 400000"))
        assert any("سقف" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_alerts_listing(self, wired, session, storage):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("دلار بالای ۲۵۰۰۰۰"))
        session.clear()
        await dispatcher.feed_update(bot, make_message_update("/alerts"))
        assert any("هشدارهای شما" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_events_command(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("دلار بالای ۲۵۰۰۰۰"))
        session.clear()
        await dispatcher.feed_update(bot, make_message_update("/events"))
        assert any("رویداد" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_alert_without_target_asks_for_number(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("دلار بالای"))
        joined = "\n".join(session.sent_texts)
        assert "هشدار" in joined  # یا لیست هشدارها یا درخواست عدد

    @pytest.mark.anyio
    async def test_callback_toggle_pauses_alert(self, wired, session, storage):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("دلار بالای ۲۵۰۰۰۰"))
        alert = storage.alerts.list_for_user(777)[0]
        await dispatcher.feed_update(bot, make_callback_update(f"alerttoggle:{alert.id}"))
        assert storage.alerts.get(alert.id, 777).status.value == "paused"

    @pytest.mark.anyio
    async def test_callback_delete_removes_alert(self, wired, session, storage):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("دلار بالای ۲۵۰۰۰۰"))
        alert = storage.alerts.list_for_user(777)[0]
        await dispatcher.feed_update(bot, make_callback_update(f"alertdel:{alert.id}"))
        assert storage.alerts.list_for_user(777) == []


class TestWatchlistCommands:
    """دیده‌بان."""

    @pytest.mark.anyio
    async def test_add_and_list(self, wired, session, storage):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_callback_update("watch:usd"))
        assert storage.watchlist.list_for_user(777) == ["usd"]
        session.clear()
        await dispatcher.feed_update(bot, make_message_update("/watchlist"))
        assert any("دیده‌بان" in text for text in session.sent_texts)

    @pytest.mark.anyio
    async def test_remove(self, wired, session, storage):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_callback_update("watch:usd"))
        await dispatcher.feed_update(bot, make_callback_update("unwatch:usd"))
        assert storage.watchlist.list_for_user(777) == []

    @pytest.mark.anyio
    async def test_empty_watchlist_message(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("/watchlist"))
        assert any("خالی است" in text for text in session.sent_texts)


class TestStatusCommand:
    """وضعیت منابع."""

    @pytest.mark.anyio
    async def test_status_reports_providers(self, wired, session):
        dispatcher, bot, _ = wired({"usd": quote()})
        await dispatcher.feed_update(bot, make_message_update("/status"))
        joined = "\n".join(session.sent_texts)
        assert "وضعیت سرویس" in joined
        assert "tgju" in joined
