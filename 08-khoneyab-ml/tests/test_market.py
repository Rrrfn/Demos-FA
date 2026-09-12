# -*- coding: utf-8 -*-
"""آزمون تحلیل بازار — همهٔ اعداد باید از کاتالوگ بیایند."""
from __future__ import annotations

from khoneyab.market import (area_bucket_stats, bedroom_stats, district_stats,
                             market_overview, model_insights, movers,
                             price_distribution, price_per_m2_distribution)


def test_overview_matches_the_catalogue(env):
    frame = env["listings"].listings_frame()
    overview = market_overview()
    assert overview["listings"] == len(frame)
    assert 0 <= overview["luxury_share"] <= 1
    assert overview["median_price"] == int(frame["price"].median())
    assert overview["median_price_m2"] == int(frame["price_per_m2"].median())


def test_district_stats_are_sorted_and_complete(env):
    frame = env["listings"].listings_frame()
    stats = district_stats()
    assert set(stats["district"]) == set(frame["district"])
    assert list(stats["median_price_m2"]) == sorted(stats["median_price_m2"], reverse=True)
    assert stats["listings"].sum() == len(frame)
    assert stats["district_name"].str.startswith("منطقه").all()
    assert not stats["short_name"].str.contains("[0-9]").any()


def test_district_values_are_real_aggregates(env):
    frame = env["listings"].listings_frame()
    stats = district_stats().set_index("district")
    for code in list(frame["district"].unique())[:3]:
        chunk = frame[frame["district"] == code]
        assert stats.loc[code, "listings"] == len(chunk)
        assert abs(stats.loc[code, "median_price"] - chunk["price"].median()) < 1.0
        assert abs(stats.loc[code, "mean_age"] - chunk["age"].mean()) < 1e-6


def test_distributions_cover_every_listing(env):
    for table in (price_distribution(), price_per_m2_distribution()):
        assert not table.empty
        assert list(table.columns) == ["center", "count"]
        assert table["count"].sum() == len(env["all"])
        assert (table["count"] >= 0).all()


def test_area_buckets_partition_the_catalogue(env):
    buckets = area_bucket_stats()
    assert len(buckets) == 6
    assert buckets["count"].sum() == len(env["all"])
    assert (buckets["median_price_m2"] > 0).all()
    assert list(buckets["count"]).count(0) == 0        # هیچ سطل خالی نمانده
    # قیمت کل با متراژ بالا می‌رود (قیمت متر مستقل از متراژ تولید می‌شود).
    assert buckets["median_price"].iloc[0] < buckets["median_price"].iloc[-1]


def test_bedroom_stats_cover_observed_counts(env):
    frame = env["listings"].listings_frame()
    stats = bedroom_stats()
    assert set(stats["bedrooms"]) == set(frame["bedrooms"])
    assert stats["count"].sum() == len(frame)
    assert (stats["median_area"] > 0).all()


def test_movers_lists_both_ends(env):
    table = movers(top=4)
    assert len(table["expensive"]) == 4
    assert len(table["affordable"]) == 4
    assert table["expensive"]["median_price_m2"].iloc[0] >= \
        table["affordable"]["median_price_m2"].iloc[0]
    assert table["expensive"]["district"].iloc[0] != table["affordable"]["district"].iloc[0]


def test_model_insights_expose_measured_metrics(env):
    insights = model_insights(env["metrics"])
    assert insights["best_model"] == env["metrics"]["best_model"]
    assert insights["r2"] > 0.85
    assert insights["cv_r2_mean"] is not None
    assert insights["n_samples"] == len(env["frame"])
    assert insights["interval"]["target_coverage_pct"] == 80
    assert len(insights["importance"]) == 8


def test_model_insights_survives_missing_metrics():
    """نبود فایل معیارها نباید صفحهٔ تحلیل را از کار بیندازد."""
    insights = model_insights({})
    assert insights["best_model"] == ""
    assert insights["r2"] is None
    assert insights["importance"] == []
