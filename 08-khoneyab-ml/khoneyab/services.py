# -*- coding: utf-8 -*-
"""لایهٔ دسترسی به داده — همهٔ صفحه‌ها از اینجا تغذیه می‌شوند.

دو تصمیم مهم در این ماژول گرفته شده که مستقیم روی سرعت سایت اثر دارند:

**۱) بارگذاری تنبل مدل.** ``scikit-learn`` حدود نیم‌ثانیه از زمان راه‌اندازی
را می‌خورد و فقط صفحه‌های «برآورد» و «جزئیات ملک» به آن نیاز دارند. اگر
بالای فایل import شود، *هر* صفحه — حتی فهرست ملک‌ها — هزینهٔ آن را می‌دهد.
اینجا import داخل تابع انجام می‌شود، پس صفحهٔ خانه و جست‌وجو تنها با
Flask و pandas بالا می‌آیند و به‌محض نخستین درخواستِ برآورد، مدل یک بار
بارگذاری می‌شود.

**۲) حافظهٔ نتیجه.** محاسبهٔ توضیح قیمت (سهم ویژگی‌ها و ملک‌های مشابه) گران
است و پاسخ آن فقط به هشت عدد مشخصات بستگی دارد. با کش کردنش، جابه‌جایی بین
آگهی‌ها و تغییر دوبارهٔ یک فیلتر به یک نگاه‌زدن به حافظه بدل می‌شود.

هیچ‌جای دیگری نباید مستقیم سراغ ماژول‌های محاسباتی برود؛ مرز داده همین
جاست و قالب‌ها فقط چیز آمادهٔ نمایش می‌گیرند.
"""
from __future__ import annotations

import json
import os
import threading
from functools import lru_cache
from typing import TYPE_CHECKING

import pandas as pd

from .config import metrics_path
from .listings import Listing, all_listings, by_id, listings_frame
from .market import (area_bucket_stats, bedroom_stats, district_stats,
                     market_overview, model_insights, movers,
                     price_distribution, price_per_m2_distribution)
from .photos import PhotoLibrary
from .search import PAGE_SIZE, SearchQuery, SearchResult, run_search

if TYPE_CHECKING:                      # فقط برای راهنمای نوع، نه در زمان اجرا
    from .explain import Explanation

#: قفل ساخت مدل — دو درخواست هم‌زمان نباید دو بار آموزش/بارگذاری راه بیندازند.
_MODEL_LOCK = threading.Lock()


# ------------------------------------------------------------------ کاتالوگ
@lru_cache(maxsize=1)
def listings() -> tuple[Listing, ...]:
    return all_listings()


@lru_cache(maxsize=2048)
def listing(identifier: str) -> Listing | None:
    return by_id(identifier)


def resolve(identifiers: list[str]) -> list[Listing]:
    """شناسه‌های معتبر به آگهی تبدیل می‌شوند؛ نامعتبرها حذف."""
    found = (listing(identifier) for identifier in identifiers if identifier)
    return [item for item in found if item is not None]


@lru_cache(maxsize=1)
def photos() -> PhotoLibrary:
    return PhotoLibrary()


# ------------------------------------------------------------------ بازار
@lru_cache(maxsize=1)
def overview() -> dict:
    return market_overview()


@lru_cache(maxsize=1)
def districts() -> pd.DataFrame:
    return district_stats()


@lru_cache(maxsize=1)
def distribution() -> pd.DataFrame:
    return price_distribution()


@lru_cache(maxsize=1)
def per_m2_distribution() -> pd.DataFrame:
    return price_per_m2_distribution()


@lru_cache(maxsize=1)
def area_buckets() -> pd.DataFrame:
    return area_bucket_stats()


@lru_cache(maxsize=1)
def bedrooms() -> pd.DataFrame:
    return bedroom_stats()


@lru_cache(maxsize=1)
def market_movers() -> dict[str, pd.DataFrame]:
    return movers()


@lru_cache(maxsize=1)
def bounds() -> dict[str, int]:
    """دامنهٔ واقعی کاتالوگ — تا فیلترها بیرون از داده نروند."""
    frame = listings_frame()
    return {
        "price_min": int(frame["price"].min()),
        "price_max": int(frame["price"].max()),
        "area_min": int(frame["area"].min()),
        "area_max": int(frame["area"].max()),
    }


# ------------------------------------------------------------------ مدل
def bundle() -> dict:
    """بستهٔ مدل — با نخستین نیاز بارگذاری می‌شود، نه در راه‌اندازی."""
    with _MODEL_LOCK:
        return _bundle_cached()


@lru_cache(maxsize=1)
def _bundle_cached() -> dict:
    from .train import load_bundle

    return load_bundle()


def metrics() -> dict:
    """معیارهای مدل. اگر فایل نباشد، آموزش راه می‌افتد."""
    path = metrics_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    from .train import train_all

    with _MODEL_LOCK:
        return train_all()


@lru_cache(maxsize=1)
def insights() -> dict:
    return model_insights(metrics())


# ------------------------------------------------------------------ برآورد
@lru_cache(maxsize=512)
def explanation(district: int, area: int, bedrooms: int, age: int, floor: int,
                parking: int, storage: int, elevator: int) -> "Explanation":
    """توضیح کامل یک برآورد — کلید کش، همان هشت مشخصهٔ ملک است."""
    from .explain import explain

    features = {
        "district": int(district), "area": int(area), "bedrooms": int(bedrooms),
        "age": int(age), "floor": int(floor), "parking": int(parking),
        "storage": int(storage), "elevator": int(elevator),
    }
    return explain(bundle(), features)


def explanation_for_listing(item: Listing) -> "Explanation":
    return explanation(item.district, item.area, item.bedrooms, item.age,
                       item.floor, item.parking, item.storage, item.elevator)


def explanation_for_features(features: dict) -> "Explanation":
    return explanation(features["district"], features["area"], features["bedrooms"],
                       features["age"], features["floor"], features["parking"],
                       features["storage"], features["elevator"])


def summary_for(explanation_value: "Explanation") -> str:
    from .explain import explanation_summary

    return explanation_summary(explanation_value)


# ------------------------------------------------------------------ جست‌وجو
@lru_cache(maxsize=256)
def search(query: SearchQuery, page_size: int = PAGE_SIZE) -> SearchResult:
    return run_search(query, page_size=page_size)


def featured(count: int = 3) -> list[Listing]:
    """آگهی‌های شاخص صفحهٔ خانه — گران‌ترین متر شهر، از دادهٔ واقعی کاتالوگ."""
    return sorted(listings(), key=lambda item: -item.price_per_m2)[:count]
