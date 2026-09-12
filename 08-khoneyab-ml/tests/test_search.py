# -*- coding: utf-8 -*-
"""آزمون جست‌وجو: فیلترها، مرتب‌سازی و صفحه‌بندی."""
from __future__ import annotations

from khoneyab.listings import listings_frame
from khoneyab.search import PAGE_SIZE, SearchQuery, default_query, run_search


def test_default_query_returns_everything(env):
    result = run_search(default_query())
    assert result.total == len(env["all"])
    assert len(result.items) == min(PAGE_SIZE, result.total)
    assert result.page == 1
    assert not default_query().is_filtered


def test_pagination_walks_without_repeating(env):
    first = run_search(default_query())
    second = run_search(default_query().with_page(2))
    assert first.has_next and not first.has_prev
    assert second.page == 2 and second.has_prev
    assert {item.id for item in first.items}.isdisjoint({item.id for item in second.items})

    last = run_search(default_query().with_page(first.pages))
    assert not last.has_next
    assert len(last.items) > 0
    seen = set()
    for page in range(1, first.pages + 1):
        seen.update(item.id for item in run_search(default_query().with_page(page)).items)
    assert len(seen) == first.total


def test_page_is_clamped_into_range(env):
    assert run_search(default_query().with_page(999)).page == run_search(default_query()).pages
    assert run_search(default_query().with_page(0)).page == 1
    assert run_search(default_query().with_page(-4)).page == 1


def test_district_filter(env):
    result = run_search(SearchQuery(districts=(1, 2, 3)))
    assert result.total > 0
    assert all(item.district in (1, 2, 3) for item in result.items)


def test_area_bounds(env):
    result = run_search(SearchQuery(area_min=100, area_max=130), page_size=200)
    assert result.total > 0
    assert all(100 <= item.area <= 130 for item in result.items)


def test_price_bounds(env):
    frame = listings_frame()
    lo = int(frame["price"].quantile(0.4))
    hi = int(frame["price"].quantile(0.6))
    result = run_search(SearchQuery(price_min=lo, price_max=hi), page_size=400)
    assert all(lo <= item.price <= hi for item in result.items)


def test_bedrooms_filter(env):
    result = run_search(SearchQuery(bedrooms=(3,)), page_size=400)
    assert result.total > 0
    assert all(item.bedrooms == 3 for item in result.items)


def test_age_filter(env):
    result = run_search(SearchQuery(age_max=5), page_size=400)
    assert all(item.age <= 5 for item in result.items)


def test_amenity_filters_are_conjunctive(env):
    result = run_search(SearchQuery(parking=True, elevator=True, storage=True), page_size=400)
    assert all(item.parking and item.elevator and item.storage for item in result.items)


def test_combined_filters_shrink_the_result(env):
    wide = run_search(SearchQuery(districts=(1,), parking=True), page_size=400)
    narrow = run_search(SearchQuery(districts=(1,), parking=True, area_min=140, area_max=190),
                        page_size=400)
    assert narrow.total <= wide.total


def test_sorting_by_price(env):
    cheap = run_search(SearchQuery(sort="ارزان‌ترین"), page_size=400).items
    dear = run_search(SearchQuery(sort="گران‌ترین"), page_size=400).items
    assert [item.price for item in cheap] == sorted(item.price for item in cheap)
    assert [item.price for item in dear] == sorted((item.price for item in dear), reverse=True)


def test_sorting_by_area_and_freshness(env):
    small = [item.area for item in run_search(SearchQuery(sort="کم‌متراژترین")).items]
    assert small == sorted(small)
    fresh = [item.days_ago for item in run_search(default_query()).items]
    assert fresh == sorted(fresh)


def test_swapped_bounds_are_repaired(env):
    """اگر کاربر حد بالا و پایین را جابه‌جا وارد کند، نتیجه خالی نباید باشد."""
    result = run_search(SearchQuery(area_min=150, area_max=90), page_size=400)
    assert result.total > 0
    assert all(90 <= item.area <= 150 for item in result.items)

    # دو سر بازه جابه‌جا داده شده‌اند؛ باید خودشان جا به‌جا شوند، نه اینکه نتیجه خالی شود.
    prices = run_search(SearchQuery(price_min=40_000_000_000, price_max=10_000_000_000),
                        page_size=400)
    assert prices.total > 0
    assert all(10_000_000_000 <= item.price <= 40_000_000_000 for item in prices.items)


def test_empty_result_is_honest(env):
    result = run_search(SearchQuery(area_min=399, area_max=400, bedrooms=(5,)))
    if result.total == 0:
        assert result.is_empty
        assert result.items == []
        assert result.median_price() == 0
        assert result.median_price_per_m2() == 0


def test_active_filter_labels(env):
    query = SearchQuery(districts=(1, 2), parking=True, age_max=10,
                        area_min=80, bedrooms=(2, 3))
    labels = query.active_filters()
    assert "2 منطقه" in labels
    assert "پارکینگ" in labels
    assert "بازهٔ متراژ" in labels
    assert "تعداد اتاق" in labels
    assert "حداکثر سن بنا" in labels
    assert query.is_filtered


def test_medians_describe_the_page(env):
    result = run_search(SearchQuery(districts=(1,)), page_size=400)
    prices = sorted(item.price for item in result.items)
    middle = prices[len(prices) // 2] if len(prices) % 2 else \
        (prices[len(prices) // 2 - 1] + prices[len(prices) // 2]) // 2
    assert abs(result.median_price() - middle) <= 1
