# -*- coding: utf-8 -*-
"""جست‌وجوی ملک — فیلتر، مرتب‌سازی و صفحه‌بندی روی کاتالوگ آگهی‌ها.

فیلترها همه اختیاری‌اند: ``None`` یعنی «مهم نیست». این تفاوت مهم است، چون
بازهٔ ۰ تا ۴۰۰ متر با «متراژ مهم نیست» یکی نیست و اگر یکی گرفته شوند، کاربر
نمی‌تواند بفهمد چرا نتیجه‌ای نمی‌بیند.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import pandas as pd

from .config import AREA_RANGE, AGE_RANGE, BEDROOM_RANGE
from .listings import Listing, all_listings, listings_frame

PAGE_SIZE = 12

#: گزینه‌های مرتب‌سازی — برچسب فارسی به نام ستون.
SORT_OPTIONS: dict[str, str] = {
    "تازه‌ترین": "days_ago",
    "ارزان‌ترین": "price",
    "گران‌ترین": "price_desc",
    "کم‌متراژترین": "area",
    "بزرگ‌ترین": "area_desc",
    "کم‌ترین قیمت متر": "price_per_m2",
    "بیشترین قیمت متر": "price_per_m2_desc",
}


@dataclass(frozen=True)
class SearchQuery:
    """مشخصات جست‌وجو. هر فیلتر خالی یعنی «بدون محدودیت»."""

    districts: tuple[int, ...] = ()
    price_min: int | None = None
    price_max: int | None = None
    area_min: int | None = None
    area_max: int | None = None
    bedrooms: tuple[int, ...] = ()
    age_max: int | None = None
    parking: bool = False
    storage: bool = False
    elevator: bool = False
    sort: str = "تازه‌ترین"
    page: int = 1

    def with_page(self, page: int) -> "SearchQuery":
        return replace(self, page=max(1, int(page)))

    def active_filters(self) -> tuple[str, ...]:
        """فهرست فیلترهای فعال — برای نشان دادن «چه چیزی فیلتر شده»."""
        labels: list[str] = []
        if self.districts:
            labels.append(f"{len(self.districts)} منطقه")
        if self.price_min is not None or self.price_max is not None:
            labels.append("بازهٔ قیمت")
        if self.area_min is not None or self.area_max is not None:
            labels.append("بازهٔ متراژ")
        if self.bedrooms:
            labels.append("تعداد اتاق")
        if self.age_max is not None:
            labels.append("حداکثر سن بنا")
        for flag, name in ((self.parking, "پارکینگ"), (self.storage, "انباری"),
                           (self.elevator, "آسانسور")):
            if flag:
                labels.append(name)
        return tuple(labels)

    @property
    def is_filtered(self) -> bool:
        return bool(self.active_filters())


@dataclass
class SearchResult:
    """نتیجهٔ جست‌وجو: صفحهٔ جاری + آمار کل."""

    items: list[Listing] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = PAGE_SIZE

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
        return not self.items

    def median_price(self) -> int:
        if not self.items:
            return 0
        return int(pd.Series([item.price for item in self.items]).median())

    def median_price_per_m2(self) -> int:
        if not self.items:
            return 0
        return int(pd.Series([item.price_per_m2 for item in self.items]).median())


def _apply(frame: pd.DataFrame, query: SearchQuery) -> pd.DataFrame:
    filtered = frame
    if query.districts:
        filtered = filtered[filtered["district"].isin(query.districts)]
    if query.price_min is not None:
        filtered = filtered[filtered["price"] >= query.price_min]
    if query.price_max is not None:
        filtered = filtered[filtered["price"] <= query.price_max]
    if query.area_min is not None:
        filtered = filtered[filtered["area"] >= query.area_min]
    if query.area_max is not None:
        filtered = filtered[filtered["area"] <= query.area_max]
    if query.bedrooms:
        filtered = filtered[filtered["bedrooms"].isin(query.bedrooms)]
    if query.age_max is not None:
        filtered = filtered[filtered["age"] <= query.age_max]
    for flag, column in ((query.parking, "parking"), (query.storage, "storage"),
                         (query.elevator, "elevator")):
        if flag:
            filtered = filtered[filtered[column] == 1]
    return filtered


def _sorted(frame: pd.DataFrame, sort: str) -> pd.DataFrame:
    column = SORT_OPTIONS.get(sort, "days_ago")
    if column.endswith("_desc"):
        return frame.sort_values(column[: -len("_desc")], ascending=False)
    return frame.sort_values(column, ascending=True)


def run_search(query: SearchQuery, *, page_size: int = PAGE_SIZE) -> SearchResult:
    """اجرای جست‌وجو و برگرداندن یک صفحه از نتیجه."""
    if query.area_min is not None and query.area_max is not None and query.area_min > query.area_max:
        query = replace(query, area_min=query.area_max, area_max=query.area_min)
    if query.price_min is not None and query.price_max is not None and query.price_min > query.price_max:
        query = replace(query, price_min=query.price_max, price_max=query.price_min)

    filtered = _sorted(_apply(listings_frame(), query), query.sort)
    total = int(len(filtered))
    pages = max(1, -(-total // page_size))
    page = min(max(1, query.page), pages)

    window = filtered.iloc[(page - 1) * page_size: page * page_size]
    lookup = {item.id: item for item in all_listings()}
    return SearchResult(
        items=[lookup[identifier] for identifier in window["id"]],
        total=total,
        page=page,
        page_size=page_size,
    )


def default_query() -> SearchQuery:
    """جست‌وجوی پیش‌فرض — همه‌چیز باز، مرتب بر تازگی."""
    return SearchQuery()


def bounds() -> dict[str, tuple[int, int]]:
    """بازهٔ مجاز فیلترها، از پیکربندی مرکزی."""
    return {"area": AREA_RANGE, "age": AGE_RANGE, "bedrooms": BEDROOM_RANGE}
