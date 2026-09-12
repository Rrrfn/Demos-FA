# -*- coding: utf-8 -*-
"""کاتالوگ آگهی‌ها — لایهٔ نمایشی روی دیتاست.

این ماژول دیتاست را به آگهی تبدیل می‌کند: هر آگهی شناسه، عنوان، توضیح، عکس و
تاریخ انتشار دارد. توجه کن که اینجا هیچ داده‌ای *تولید* نمی‌شود؛ همهٔ مقادیر
از همان رکوردهای دیتاست می‌آید و فقط برچسب نمایشی به آن‌ها اضافه می‌شود. اگر
جایی عددی با دیتاست نخواند، یعنی باگ است.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field

import pandas as pd

from .config import (LUXURY_AREA_THRESHOLD, N_LISTINGS, RANDOM_SEED,
                     DISTRICT_BY_CODE, district_factor)
from .dataset import get_dataset
from .labels import bedrooms_label, district_name, fa_number, floor_label
from .photos import PhotoLibrary

#: بازهٔ «تازه» بودن آگهی — برای مرتب‌سازی بر اساس تازگی.
MAX_DAYS_AGO = 90


@dataclass(frozen=True)
class Listing:
    """یک آگهی ملک."""

    id: str
    index: int
    district: int
    area: int
    bedrooms: int
    age: int
    floor: int
    parking: int
    storage: int
    elevator: int
    price: int
    title: str
    description: str
    property_type: str
    days_ago: int
    gallery: tuple[str, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------ ویژگی‌های مشتق
    @property
    def price_per_m2(self) -> int:
        return int(self.price / self.area) if self.area else 0

    @property
    def district_label(self) -> str:
        return district_name(self.district)

    @property
    def bedrooms_label(self) -> str:
        return bedrooms_label(self.bedrooms)

    @property
    def floor_label(self) -> str:
        return floor_label(self.floor)

    @property
    def is_luxury(self) -> bool:
        return self.area >= LUXURY_AREA_THRESHOLD

    @property
    def amenities(self) -> tuple[str, ...]:
        names = []
        if self.parking:
            names.append("پارکینگ")
        if self.storage:
            names.append("انباری")
        if self.elevator:
            names.append("آسانسور")
        return tuple(names)

    @property
    def cover(self) -> str | None:
        return self.gallery[0] if self.gallery else None

    def as_features(self) -> dict:
        """دیکشنری ورودی مدل — ترتیب کلیدها مطابق ``config.FEATURES``."""
        return {
            "district": self.district, "area": self.area, "bedrooms": self.bedrooms,
            "age": self.age, "floor": self.floor, "parking": self.parking,
            "storage": self.storage, "elevator": self.elevator,
        }


def _condition_phrase(age: int) -> str:
    if age <= 2:
        return "کلیدنخورده"
    if age <= 8:
        return "نوساز"
    if age <= 20:
        return "سالم"
    return "نیازمند بازسازی"


def _property_type(area: int, floor: int) -> str:
    if floor <= 0 and area >= 150:
        return "خانهٔ ویلایی"
    if floor >= 5:
        return "آپارتمان برجی"
    if floor < 0:
        return "واحد زیرزمین"
    return "آپارتمان"


def _title(row: dict, district_name_text: str) -> str:
    kind = row["property_type"]
    return (f"{kind} {fa_number(row['area'])} متری، "
            f"{bedrooms_label(row['bedrooms'])}، {district_name_text}")


def _description(row: dict, district_text: str) -> str:
    parts = [
        f"{row['property_type']} با {fa_number(row['area'])} مترمربع زیربنا و "
        f"{bedrooms_label(row['bedrooms'])}، واقع در {district_text}.",
        f"سن بنا {fa_number(row['age'])} سال ({_condition_phrase(row['age'])}) و "
        f"{floor_label(row['floor'])}.",
    ]
    amenity_map = {"parking": "پارکینگ", "storage": "انباری", "elevator": "آسانسور"}
    have = [label for key, label in amenity_map.items() if row[key]]
    missing = [label for key, label in amenity_map.items() if not row[key]]
    if have:
        parts.append("امکانات: " + "، ".join(have) + ".")
    if missing:
        parts.append("بدون " + "، ".join(missing) + ".")
    return " ".join(parts)


def _build(listings_count: int, seed: int) -> tuple[Listing, ...]:
    frame = get_dataset()
    if len(frame) < listings_count:
        listings_count = len(frame)

    # نمونه‌گیری پایدار: بدون seed تصادفی، فقط گام ثابت روی ردیف‌های دیتاست.
    step = max(1, len(frame) // listings_count)
    subset = frame.iloc[::step].head(listings_count).reset_index(drop=True)

    photos = PhotoLibrary()
    built: list[Listing] = []
    for index, record in enumerate(subset.to_dict("records")):
        district = int(record["district"])
        district_text = district_name(district)
        area = int(record["area"])
        floor = int(record["floor"])
        row = {
            "property_type": _property_type(area, floor),
            "area": area,
            "bedrooms": int(record["bedrooms"]),
            "age": int(record["age"]),
            "floor": floor,
            "parking": int(record["parking"]),
            "storage": int(record["storage"]),
            "elevator": int(record["elevator"]),
        }
        built.append(Listing(
            id=f"KH-{index + 1001}",
            index=index,
            district=district,
            area=area,
            bedrooms=row["bedrooms"],
            age=row["age"],
            floor=floor,
            parking=row["parking"],
            storage=row["storage"],
            elevator=row["elevator"],
            price=int(record["price"]),
            title=_title(row, district_text),
            description=_description(row, district_text),
            property_type=row["property_type"],
            days_ago=(index * 7 + seed) % MAX_DAYS_AGO,
            gallery=photos.gallery(index),
        ))
    return tuple(built)


@functools.lru_cache(maxsize=1)
def all_listings() -> tuple[Listing, ...]:
    """همهٔ آگهی‌ها — یک بار ساخته و نگه داشته می‌شود."""
    return _build(N_LISTINGS, RANDOM_SEED)


@functools.lru_cache(maxsize=1)
def listings_frame() -> pd.DataFrame:
    """آگهی‌ها به شکل جدول — برای فیلتر و نمودار سریع."""
    rows = [{
        "id": item.id, "district": item.district, "area": item.area,
        "bedrooms": item.bedrooms, "age": item.age, "floor": item.floor,
        "parking": item.parking, "storage": item.storage, "elevator": item.elevator,
        "price": item.price, "price_per_m2": item.price_per_m2,
        "days_ago": item.days_ago,
    } for item in all_listings()]
    return pd.DataFrame(rows)


def by_id(listing_id: str) -> Listing | None:
    for item in all_listings():
        if item.id == listing_id:
            return item
    return None


def clear_cache() -> None:
    """پاک‌کردن کش — آزمون‌ها پس از تغییر دیتاست به آن نیاز دارند."""
    all_listings.cache_clear()
    listings_frame.cache_clear()
