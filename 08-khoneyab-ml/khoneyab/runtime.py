# -*- coding: utf-8 -*-
"""لایهٔ اجرا — بارگذاری و کش کردن منابع سنگین.

مدل، دیتاست و تجمیع‌های بازار گران‌اند و در هر تعامل کاربر نباید از نو ساخته
شوند. اینجا همه با کش Streamlit نگه داشته می‌شوند تا جابه‌جایی بین صفحه‌ها
بی‌درنگ باشد. توابع این ماژول تنها جایی هستند که رابط با «داده» تماس دارد.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .dataset import get_dataset
from .explain import Explanation, explain, explanation_summary
from .listings import Listing, all_listings, by_id, listings_frame
from .market import (area_bucket_stats, bedroom_stats, district_stats,
                     market_overview, model_insights, movers,
                     price_distribution, price_per_m2_distribution)
from .photos import PhotoLibrary
from .search import SearchQuery, run_search
from .train import load_bundle, load_metrics

SPINNER_MODEL = "در حال آماده‌سازی مدل…"


@st.cache_resource(show_spinner=SPINNER_MODEL)
def bundle() -> dict:
    """بستهٔ آموزش‌دیدهٔ مدل — یک بار در طول عمر پروسه."""
    return load_bundle()


@st.cache_data(show_spinner=False)
def metrics() -> dict:
    return load_metrics()


@st.cache_data(show_spinner=False)
def insights() -> dict:
    return model_insights(load_metrics())


@st.cache_data(show_spinner=False)
def dataset() -> pd.DataFrame:
    return get_dataset()


@st.cache_data(show_spinner=False)
def listings() -> tuple[Listing, ...]:
    return all_listings()


@st.cache_data(show_spinner=False)
def listing(listing_id: str) -> Listing | None:
    return by_id(listing_id)


@st.cache_data(show_spinner=False)
def overview() -> dict:
    return market_overview()


@st.cache_data(show_spinner=False)
def listings_frame_bounds() -> dict:
    """کمینه و بیشینهٔ واقعی کاتالوگ — تا دامنهٔ اسلایدرها با داده بخواند."""
    frame = listings_frame()
    return {
        "price_min": int(frame["price"].min()),
        "price_max": int(frame["price"].max()),
        "area_min": int(frame["area"].min()),
        "area_max": int(frame["area"].max()),
    }


@st.cache_data(show_spinner=False)
def districts() -> pd.DataFrame:
    return district_stats()


@st.cache_data(show_spinner=False)
def distribution() -> pd.DataFrame:
    return price_distribution()


@st.cache_data(show_spinner=False)
def per_m2_distribution() -> pd.DataFrame:
    return price_per_m2_distribution()


@st.cache_data(show_spinner=False)
def area_buckets() -> pd.DataFrame:
    return area_bucket_stats()


@st.cache_data(show_spinner=False)
def bedrooms() -> pd.DataFrame:
    return bedroom_stats()


@st.cache_data(show_spinner=False)
def market_movers() -> dict[str, pd.DataFrame]:
    return movers()


@st.cache_data(show_spinner=False)
def search(districts_tuple: tuple[int, ...], price_range: tuple[int, int],
           area_range: tuple[int, int], bedrooms_tuple: tuple[int, ...],
           age_max: int, parking: bool, storage: bool, elevator: bool,
           sort: str, page: int) -> "SearchResultView":
    query = SearchQuery(
        districts=districts_tuple,
        price_min=price_range[0], price_max=price_range[1],
        area_min=area_range[0], area_max=area_range[1],
        bedrooms=bedrooms_tuple, age_max=age_max,
        parking=parking, storage=storage, elevator=elevator,
        sort=sort, page=page,
    )
    return SearchResultView(run_search(query))


@st.cache_data(show_spinner="در حال محاسبهٔ ارزش برآوردی…")
def explanation(district: int, area: int, bedrooms: int, age: int, floor: int,
                parking: int, storage: int, elevator: int) -> tuple[Explanation, str]:
    """توضیح کامل یک پیش‌بینی + خلاصهٔ متنی — کش‌شده بر پایهٔ مشخصات."""
    features = {"district": district, "area": area, "bedrooms": bedrooms,
                "age": age, "floor": floor, "parking": parking,
                "storage": storage, "elevator": elevator}
    result = explain(load_bundle(), features)
    return result, explanation_summary(result)


@st.cache_data(show_spinner=False)
def photos() -> PhotoLibrary:
    return PhotoLibrary()


class SearchResultView:
    """نسخهٔ قابل‌کش نتیجهٔ جست‌وجو.

    ``SearchResult`` خودش dataclass است و برای کش‌کردن باید قابل هش باشد؛ این
    پوسته فقط شناسه‌ها و آمار را نگه می‌دارد و کارت‌ها هنگام نمایش از
    :func:`listing` خوانده می‌شوند.
    """

    def __init__(self, result) -> None:
        self.ids: tuple[str, ...] = tuple(item.id for item in result.items)
        self.total: int = result.total
        self.page: int = result.page
        self.page_size: int = result.page_size

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def is_empty(self) -> bool:
        return not self.ids

    def items(self) -> list[Listing]:
        found = (by_id(identifier) for identifier in self.ids)
        return [item for item in found if item is not None]

    def median_price(self) -> int:
        values = [item.price for item in self.items()]
        return int(pd.Series(values).median()) if values else 0

    def median_price_per_m2(self) -> int:
        values = [item.price_per_m2 for item in self.items()]
        return int(pd.Series(values).median()) if values else 0
