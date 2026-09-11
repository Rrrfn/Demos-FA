# -*- coding: utf-8 -*-
"""آزمون لایهٔ وب — پوشش یکدست، اعتبارسنجی، صفحه‌بندی و کدهای خطا.

هر پاسخ API باید یکی از این دو شکل باشد و هیچ مسیری نباید استثنا بیرون بدهد:

    {"ok": true,  "data": {...}, "error": null}
    {"ok": false, "data": null,  "error": {"code", "message"}}

به همین دلیل هر آزمون از همین دو دست‌آویز استفاده می‌کند؛ اگر روزی مسیری
پاسخ بی‌پوشش برگرداند، همین‌جا شکست می‌خورد.
"""
from __future__ import annotations

import json
import time

import pytest

from cheshmbaz.core.models import Quote


# ------------------------------------------------------------------ helpers
def _store(storage, slug: str, price: float, *, age_seconds: float = 30.0, **kwargs) -> Quote:
    stamp = time.time() - age_seconds
    quote = Quote(
        slug=slug,
        price=price,
        unit="usd" if slug in {"bitcoin", "ethereum"} else "toman",
        source="test",
        observed_at=stamp,
        fetched_at=stamp,
        **kwargs,
    )
    storage.quotes.save_many({slug: quote})
    return quote


def _data(response):
    """پاسخ موفق را باز می‌کند و پوشش را تأیید می‌کند."""
    assert response.status_code < 400, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert "data" in payload
    return payload["data"]


def _error(response, *, status: int, code: str | None = None):
    """پاسخ ناموفق را باز می‌کند و پوشش را تأیید می‌کند."""
    assert response.status_code == status, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert {"code", "message"} <= set(payload["error"])
    if code is not None:
        assert payload["error"]["code"] == code
    return payload["error"]


# -------------------------------------------------------------------- basics
def test_dashboard_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "cheshmbaz" in body.lower() or "چشم‌باز" in body


def test_health_never_fetches_from_network(client):
    health = _data(client.get("/health"))
    assert health["status"] == "ok"
    assert health["engine_ready"] is True
    assert health["quotes"] == 0
    assert health["database"]["schema_version"] >= 1


def test_api_index_documents_endpoints(client):
    docs = _data(client.get("/api/v1"))
    assert docs["version"]
    assert any("/api/v1/overview" in item for item in docs["endpoints"])


def test_meta_exposes_registry_and_thresholds(client):
    meta = _data(client.get("/api/v1/meta"))
    assert meta["environment"] == "testing"
    slugs = {asset["slug"] for asset in meta["assets"]}
    assert {"geram18", "usd", "bitcoin", "ethereum"} <= slugs
    assert [item["key"] for item in meta["ranges"]] == ["1D", "7D", "30D", "90D"]
    assert meta["thresholds"]["live_within"] == 1800
    assert {item["value"] for item in meta["alert_kinds"]} == {"above", "below", "pct_move"}


# ------------------------------------------------------------------ overview
def test_overview_groups_cards_and_sources(client, storage):
    _store(storage, "usd", 200_000)
    _store(storage, "bitcoin", 77_000)

    data = _data(client.get("/api/v1/overview"))
    assert [group["kind"] for group in data["groups"]] == ["gold", "coin", "currency", "crypto"]
    assert data["totals"]["with_data"] == 2
    assert data["totals"]["usable"] == 2
    assert len(data["featured"]) == 6
    assert data["totals"]["missing"] == data["totals"]["assets"] - 2
    assert isinstance(data["sources"], list)


def test_digest_is_light_and_formats_persian_numbers(client, storage):
    _store(storage, "usd", 200_000)
    digest = _data(client.get("/api/v1/digest"))
    assert len(digest["items"]) == 6
    assert digest["generated_at"] > 0
    usd = next(item for item in digest["items"] if item["slug"] == "usd")
    # اعداد باید با ارقام فارسی و جداکنندهٔ فارسی نمایش داده شوند
    assert not any(char.isdigit() and char.isascii() for char in usd["price_text"])
    assert "۲۰۰" in usd["price_text"]


def test_missing_asset_card_is_explicit_not_fabricated(client):
    data = _data(client.get("/api/v1/assets/solana"))
    assert data["has_data"] is False
    assert data["price"] is None
    assert data["price_text"] == "—"
    assert data["freshness"] == "unknown"


# -------------------------------------------------------------------- assets
def test_assets_pagination_walks_the_registry(client):
    first = _data(client.get("/api/v1/assets?page=1&page_size=3"))
    assert len(first["items"]) == 3
    assert first["pagination"]["page"] == 1
    assert first["pagination"]["has_next"] is True

    total = first["pagination"]["total"]
    last = _data(client.get(f"/api/v1/assets?page=1&page_size={total}"))
    assert len(last["items"]) == total
    assert last["pagination"]["has_next"] is False

    beyond = _data(client.get("/api/v1/assets?page=99&page_size=3"))
    assert beyond["items"] == []


def test_assets_kind_filter(client):
    data = _data(client.get("/api/v1/assets?kind=crypto&page_size=50"))
    assert data["items"]
    assert all(item["kind"] == "crypto" for item in data["items"])


def test_assets_reject_invalid_kind(client):
    error = _error(client.get("/api/v1/assets?kind=nope"), status=400, code="validation_error")
    assert error["field"] == "kind"


@pytest.mark.parametrize("query", ["page=0", "page=abc", "page_size=0", "page_size=-2"])
def test_assets_reject_bad_pagination(client, query):
    _error(client.get(f"/api/v1/assets?{query}"), status=400, code="validation_error")


def test_assets_page_size_is_clamped_not_rejected(client):
    data = _data(client.get("/api/v1/assets?page_size=99999"))
    assert data["pagination"]["page_size"] == 50  # max_page_size در پیکربندی تست


def test_asset_detail_includes_coverage_and_ranges(client, storage):
    _store(storage, "usd", 200_000)
    detail = _data(client.get("/api/v1/assets/usd"))
    assert detail["slug"] == "usd"
    assert detail["has_data"] is True
    assert detail["watchlist"] is False
    assert detail["coverage"]["points"] == 0  # قیمت ذخیره شده، ولی تاریخچه‌ای ثبت نشده
    assert [item["key"] for item in detail["ranges"]] == ["1D", "7D", "30D", "90D"]


def test_unknown_asset_returns_404_unknown_asset(client):
    error = _error(client.get("/api/v1/assets/does-not-exist"), status=404, code="unknown_asset")
    assert "does-not-exist" in error["message"]


# -------------------------------------------------------------------- series
def test_series_returns_real_points_only(client, storage):
    now = time.time()
    for index in range(6):
        storage.history.record_many({
            "usd": Quote(slug="usd", price=200_000 + index * 100, unit="toman", source="test",
                         observed_at=now - (6 - index) * 1200, fetched_at=now)
        })
    series = _data(client.get("/api/v1/assets/usd/series?range=1D"))
    assert series["range"] == "1D"
    assert series["has_data"] is True
    assert series["count"] == len(series["points"]) >= 2
    timestamps = [point["ts"] for point in series["points"]]
    assert timestamps == sorted(timestamps)


def test_series_is_honest_when_empty(client):
    series = _data(client.get("/api/v1/assets/usd/series?range=90D"))
    assert series["points"] == []
    assert series["has_data"] is False


def test_series_falls_back_to_default_range_when_unknown(client):
    series = _data(client.get("/api/v1/assets/usd/series?range=nonsense"))
    assert series["range"] == "7D"


# -------------------------------------------------------------------- movers
def test_movers_window_and_limit(client, storage):
    now = time.time()
    storage.history.record_many({
        "usd": Quote(slug="usd", price=200_000, unit="toman", source="test",
                     observed_at=now - 90_000, fetched_at=now - 90_000),
    })
    _store(storage, "usd", 220_000)

    data = _data(client.get("/api/v1/movers?window=1D&limit=3"))
    assert data["window"] == "1D"
    assert data["window_label"] == "۲۴ ساعت"
    assert [item["slug"] for item in data["gainers"]] == ["usd"]
    assert data["gainers"][0]["change_pct_text"] == "۱۰٪"


def test_movers_unknown_window_reports_effective_window(client):
    data = _data(client.get("/api/v1/movers?window=forever"))
    assert data["window"] == "1D"
    assert data["window_label"] == "۲۴ ساعت"


def test_movers_reject_out_of_range_limit(client):
    _error(client.get("/api/v1/movers?limit=0"), status=400, code="validation_error")
    _error(client.get("/api/v1/movers?limit=abc"), status=400, code="validation_error")
    # سقف بالا بریده می‌شود، نه اینکه درخواست رد شود
    data = _data(client.get("/api/v1/movers?limit=9999"))
    assert data["window"] == "1D"


# -------------------------------------------------------------------- search
def test_search_finds_assets_by_persian_name(client, storage):
    _store(storage, "usd", 200_000)
    data = _data(client.get("/api/v1/search?q=دلار"))
    assert [card["slug"] for card in data["items"]] == ["usd"]
    assert data["query"] == "دلار"


def test_search_empty_query_returns_nothing(client):
    assert _data(client.get("/api/v1/search"))["items"] == []
    assert _data(client.get("/api/v1/search?q="))["items"] == []


def test_search_rejects_overlong_query(client):
    _error(client.get("/api/v1/search?q=" + "x" * 65), status=400, code="validation_error")


# ---------------------------------------------------------------- diagnostics
def test_sources_endpoint_reports_health_shape(client):
    data = _data(client.get("/api/v1/sources"))
    names = {item["name"] for item in data["items"]}
    assert {"tgju", "coingecko"} <= names
    assert "database" in data


def test_status_endpoint_reports_scheduler(client):
    data = _data(client.get("/api/v1/status"))
    assert data["scheduler"]["running"] is False  # زمان‌بند در تست روشن نمی‌شود
    assert data["database"]["schema_version"] >= 1
    assert data["server_time"] > 0


# ----------------------------------------------------------------- watchlist
def test_watchlist_add_list_and_remove(client, storage):
    _store(storage, "usd", 200_000)

    empty = _data(client.get("/api/v1/watchlist"))
    assert empty["count"] == 0

    added = _data(client.post("/api/v1/watchlist/usd"))
    assert added["in_watchlist"] is True
    assert added["count"] == 1

    listed = _data(client.get("/api/v1/watchlist"))
    assert listed["count"] == 1
    assert listed["items"][0]["slug"] == "usd"
    assert listed["items"][0]["added_at"] > 0

    # همان درخواست دوباره یعنی برداشتن — دکمهٔ ستاره
    toggled = _data(client.post("/api/v1/watchlist/usd"))
    assert toggled["in_watchlist"] is False
    assert toggled["count"] == 0

    _data(client.post("/api/v1/watchlist/usd"))
    removed = _data(client.delete("/api/v1/watchlist/usd"))
    assert removed["removed"] is True
    assert removed["count"] == 0

    again = _data(client.delete("/api/v1/watchlist/usd"))
    assert again["removed"] is False


def test_watchlist_unknown_slug_is_404(client):
    _error(client.post("/api/v1/watchlist/nope"), status=404, code="unknown_asset")


def test_watchlist_is_isolated_per_visitor(client, storage):
    _store(storage, "usd", 200_000)
    _data(client.post("/api/v1/watchlist/usd", headers={"X-Owner": "visitor-a"}))
    other = _data(client.get("/api/v1/watchlist", headers={"X-Owner": "visitor-b"}))
    assert other["count"] == 0


# -------------------------------------------------------------------- alerts
def _create_rule(client, **overrides):
    payload = {"slug": "usd", "kind": "above", "threshold": 300_000}
    payload.update(overrides)
    return client.post("/api/v1/alerts", json=payload)


def test_create_alert_rule(client, storage):
    _store(storage, "usd", 200_000)
    data = _data(_create_rule(client, note="گارد فروش"))
    rule = data["rule"]
    assert rule["slug"] == "usd"
    assert rule["kind"] == "above"
    assert rule["status"] == "active"
    assert rule["threshold"] == 300_000
    assert rule["kind_label"] == "بالاتر از"
    assert data["title"] == "دلار آمریکا"
    assert rule["id"] > 0


def test_alert_list_includes_distance_to_threshold(client, storage):
    _store(storage, "usd", 200_000)
    _create_rule(client, threshold=300_000)
    view = _data(client.get("/api/v1/alerts"))
    assert view["count"] == 1
    entry = view["items"][0]
    assert entry["current_price"] == 200_000
    assert entry["is_usable"] is True
    assert entry["distance_pct"] == pytest.approx(-33.33, abs=0.1)
    assert view["pagination"]["page"] == 1
    assert view["stats"]["rules"] == 1


def test_alert_list_filters_by_slug(client, storage):
    _store(storage, "usd", 200_000)
    _create_rule(client)
    assert _data(client.get("/api/v1/alerts?slug=usd"))["count"] == 1
    assert _data(client.get("/api/v1/alerts?slug=eur"))["count"] == 0
    _error(client.get("/api/v1/alerts?slug=nope"), status=404, code="unknown_asset")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"kind": "above", "threshold": 1}, "slug"),
        ({"slug": "usd", "threshold": 1}, "kind"),
        ({"slug": "usd", "kind": "sideways", "threshold": 1}, "kind"),
        ({"slug": "usd", "kind": "above"}, "threshold"),
        ({"slug": "usd", "kind": "above", "threshold": "زیاد"}, "threshold"),
    ],
)
def test_alert_creation_validation(client, payload, field):
    response = client.post("/api/v1/alerts", json=payload)
    error = _error(response, status=400, code="validation_error")
    assert error["field"] == field


def test_alert_creation_rejects_unknown_slug(client):
    error = _error(_create_rule(client, slug="planet-x"), status=400, code="validation_error")
    assert error["field"] == "slug"


def test_alert_creation_rejects_empty_body(client):
    error = _error(client.post("/api/v1/alerts"), status=400, code="validation_error")
    assert error["field"] == "slug"


def test_alert_creation_rejects_malformed_json(client):
    response = client.post(
        "/api/v1/alerts", data="{not json", content_type="application/json"
    )
    error = _error(response, status=400, code="validation_error")
    assert error["field"] == "body"


def test_alert_threshold_bounds_are_domain_validated(client):
    error = _error(_create_rule(client, threshold=0), status=400, code="validation_error")
    assert error["field"] == "threshold"


def test_alert_pause_and_resume(client, storage):
    _store(storage, "usd", 200_000)
    rule_id = _data(_create_rule(client))["rule"]["id"]

    paused = _data(client.patch(f"/api/v1/alerts/{rule_id}", json={"status": "paused"}))
    assert paused["rule"]["status"] == "paused"
    assert _data(client.get("/api/v1/alerts?page_size=50"))["items"][0]["status"] == "paused"

    resumed = _data(client.patch(f"/api/v1/alerts/{rule_id}", json={"status": "active"}))
    assert resumed["rule"]["status"] == "active"


def test_alert_patch_rejects_bad_status(client, storage):
    _store(storage, "usd", 200_000)
    rule_id = _data(_create_rule(client))["rule"]["id"]
    error = _error(
        client.patch(f"/api/v1/alerts/{rule_id}", json={"status": "maybe"}),
        status=400, code="validation_error",
    )
    assert error["field"] == "status"


def test_alert_patch_unknown_rule_is_404(client):
    error = _error(
        client.patch("/api/v1/alerts/424242", json={"status": "active"}),
        status=404, code="rule_not_found",
    )
    # پیام فارسی، با ارقام فارسی و بدون جداکنندهٔ هزارگان روی شناسه
    assert "۴۲۴۲۴۲" in error["message"]
    assert "٬" not in error["message"]
    assert not any(char.isdigit() and char.isascii() for char in error["message"])


def test_alert_delete(client, storage):
    _store(storage, "usd", 200_000)
    rule_id = _data(_create_rule(client))["rule"]["id"]
    assert _data(client.delete(f"/api/v1/alerts/{rule_id}"))["deleted"] is True
    assert _data(client.get("/api/v1/alerts"))["count"] == 0
    _error(client.delete(f"/api/v1/alerts/{rule_id}"), status=404, code="rule_not_found")


def test_alert_preview_is_advisory_only(client, storage):
    _store(storage, "usd", 200_000)
    would_fire = _data(client.post(
        "/api/v1/alerts/preview", json={"slug": "usd", "kind": "above", "threshold": 100_000}
    ))
    assert would_fire["would_fire"] is True
    assert would_fire["current_price_text"]

    would_not = _data(client.post(
        "/api/v1/alerts/preview", json={"slug": "usd", "kind": "above", "threshold": 900_000}
    ))
    assert would_not["would_fire"] is False

    # پیش‌نمایش نباید قاعده‌ای بسازد
    assert _data(client.get("/api/v1/alerts"))["count"] == 0


def test_alert_preview_says_so_when_feed_is_stale(client, storage):
    _store(storage, "usd", 200_000, age_seconds=300_000)
    result = _data(client.post(
        "/api/v1/alerts/preview", json={"slug": "usd", "kind": "above", "threshold": 1}
    ))
    assert result["would_fire"] is False
    assert "تازه نیست" in result["reason"]


def test_events_log_is_empty_until_evaluation(client, storage):
    _store(storage, "usd", 200_000)
    _create_rule(client, threshold=1)
    view = _data(client.get("/api/v1/events"))
    assert view["count"] == 0
    assert view["stats"]["rules"] == 1


def test_events_can_hide_suppressed_ones(client, storage):
    _store(storage, "usd", 200_000)
    rule_id = _data(_create_rule(client, threshold=1))["rule"]["id"]
    storage.alerts.log_event(
        slug="usd", kind="above", price=1, threshold=0, message="رخداد", rule_id=rule_id
    )
    storage.alerts.log_event(
        slug="usd", kind="above", price=1, threshold=0, message="مهار",
        rule_id=rule_id, suppressed=True, reason="خنک‌شدن",
    )
    assert _data(client.get("/api/v1/events"))["count"] == 2
    visible = _data(client.get("/api/v1/events?suppressed=0"))
    assert visible["count"] == 1
    assert visible["items"][0]["message"] == "رخداد"


# ------------------------------------------------------------------- actions
def test_collect_endpoint_reports_result(client):
    """جمع‌آوری دستی روی پاسخ‌های ضبط‌شده — بدون شبکه."""
    data = _data(client.post("/api/v1/collect"))
    assert data["ok"] is True
    assert data["quotes_received"] > 0
    assert data["quotes_saved"] > 0
    providers = {run["name"]: run for run in data["providers"]}
    assert providers["tgju"]["received"] > 0
    assert providers["coingecko"]["received"] > 0

    # و داده واقعاً در پایگاه نشسته است
    health = _data(client.get("/health"))
    assert health["quotes"] > 0


def test_collect_does_not_duplicate_source_timestamped_readings(client, storage):
    """رمزارز زمان مشاهدهٔ خود منبع را می‌دهد؛ دور دوم نباید رکورد تکراری بسازد."""
    _data(client.post("/api/v1/collect"))
    before = storage.history.coverage("bitcoin")["points"]
    assert before >= 1
    _data(client.post("/api/v1/collect"))
    assert storage.history.coverage("bitcoin")["points"] == before


def test_collect_works_in_production_when_no_token_is_configured(config, storage, live_providers):
    """دموی تولیدی بدون توکن باید کار کند؛ وگرنه دکمهٔ «واکشی تازه» مرده است."""
    from cheshmbaz.context import AppContext
    from cheshmbaz.webapp import create_app

    production = config.retuned(env="production", admin_token="")
    context = AppContext.build(production, storage=storage, providers=live_providers)
    app = create_app(context)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        assert _data(client.post("/api/v1/collect"))["quotes_received"] > 0


def test_wsgi_entry_point_bootstraps_the_scheduler(monkeypatch, tmp_path):
    """مسیر تولیدی gunicorn باید زمان‌بند را روشن کند، وگرنه جمع‌آوری خودکار نداریم."""
    from cheshmbaz import webapp as webapp_module

    monkeypatch.setenv("CHESHMAZ_ENV", "production")
    monkeypatch.setenv("COLLECT_ENABLED", "1")
    monkeypatch.setenv("CHESHMAZ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHESHMAZ_DB_PATH", str(tmp_path / "wsgi.db"))

    app = webapp_module._default_app()
    context = app.extensions["cheshmbaz"]
    try:
        assert context.scheduler.is_running is True
    finally:
        context.shutdown()


def test_create_app_stays_side_effect_free(config, storage, live_providers):
    """آزمون‌ها و ابزارها نباید ناخواسته زمان‌بند روشن کنند."""
    from cheshmbaz.context import AppContext
    from cheshmbaz.webapp import create_app

    eager = config.retuned(collector={"enabled": True, "interval_seconds": 1800})
    context = AppContext.build(eager, storage=storage, providers=live_providers)
    app = create_app(context)
    assert app.extensions["cheshmbaz"].scheduler.is_running is False


def test_collect_requires_admin_token_when_configured(config, storage, live_providers):
    from cheshmbaz.context import AppContext
    from cheshmbaz.webapp import create_app

    secured = config.retuned(admin_token="s3cret")
    context = AppContext.build(secured, storage=storage, providers=live_providers)
    app = create_app(context)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        error = _error(client.post("/api/v1/collect"), status=400, code="validation_error")
        assert error["field"] == "token"
        _error(
            client.post("/api/v1/collect", headers={"X-Admin-Token": "wrong"}),
            status=400, code="validation_error",
        )
        assert client.post(
            "/api/v1/collect", headers={"X-Admin-Token": "s3cret"}
        ).status_code == 200


def test_evaluate_endpoint_runs_the_engine(client, storage):
    _store(storage, "usd", 200_000)
    _create_rule(client, threshold=1)
    outcome = _data(client.post("/api/v1/alerts/evaluate"))
    assert outcome["checked"] == 1
    assert outcome["notified"] == 1
    assert _data(client.get("/api/v1/events"))["count"] == 1


# -------------------------------------------------------------- error layer
def test_unknown_route_uses_the_same_envelope(client):
    _error(client.get("/api/v1/nowhere"), status=404, code="not_found")


def test_wrong_method_uses_the_same_envelope(client):
    _error(client.delete("/api/v1/overview"), status=405, code="method_not_allowed")


def test_html_is_not_served_for_api_paths(client):
    response = client.get("/api/v1/nowhere")
    assert response.mimetype == "application/json"


def test_internal_error_is_never_leaked(client, monkeypatch):
    """خطای غیرمنتظره باید ۵۰۰ با پوشش باشد، بدون ردپای پایتون در پاسخ."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("cheshmbaz.services.market.MarketService.overview", boom)
    error = _error(client.get("/api/v1/overview"), status=500, code="internal_error")
    assert "secret internal detail" not in json.dumps(error, ensure_ascii=False)
    assert "Traceback" not in error["message"]
