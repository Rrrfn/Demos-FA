# -*- coding: utf-8 -*-
"""توضیح پیش‌بینی — «چرا این عدد؟»

کاربر نباید فقط یک قیمت ببیند. این ماژول سه چیز قابل بررسی می‌سازد:

**۱) اثر هر ویژگی.** از ملک مرجع شروع می‌کنیم و ویژگی‌ها را یکی‌یکی به مقدار
ملک واقعی می‌بریم؛ هر گام، قیمت را به‌اندازه‌ای جابه‌جا می‌کند و همان جابه‌جایی
سهم آن ویژگی است. این روش مستقل از نوع مدل است.

ترتیب برداشتن ویژگی‌ها روی نتیجه اثر دارد. برای همین یک ترتیب کافی نیست: چند
ترتیب مختلف اجرا و سهم هر ویژگی میان آن‌ها میانگین گرفته می‌شود. مزیت مهم این
کار آن است که مجموع سهم‌ها **دقیقاً** برابر اختلاف با ملک مرجع می‌ماند، پس هیچ
«باقی‌ماندهٔ توضیح‌داده‌نشده‌ای» در گزارش نمی‌ماند.

**۲) بازهٔ اطمینان.** از مدل‌های چندکی می‌آید، نه از یک قاعدهٔ تجربی.

**۳) ملک‌های مشابه.** نزدیک‌ترین آگهی‌های کاتالوگ بر پایهٔ منطقه، متراژ، سن و
اتاق — تا کاربر عدد را با نمونه‌های واقعی همین کاتالوگ بسنجد.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import FEATURES, RANDOM_SEED
from .dataset import get_dataset
from .labels import (fa_number, feature_delta_label, feature_value_label)
from .listings import Listing, all_listings
from .train import predict, predict_interval

#: تعداد ترتیب‌هایی که برای میانگین‌گیری سهم ویژگی‌ها اجرا می‌شود. یک ترتیب
#: کافی نیست و همهٔ ترتیب‌ها (۸! = ۴۰٬۳۲۰) هم گران است؛ این تعداد، اثر ترتیب را
#: تا حد خوبی خنثی می‌کند و مجموع سهم‌ها را دقیق نگه می‌دارد.
ATTRIBUTION_ORDERS = 12

#: دامنهٔ جست‌وجوی ملک‌های مشابه.
COMPARABLE_AREA_TOLERANCE = 0.20      # ±۲۰٪ متراژ
COMPARABLE_AGE_TOLERANCE = 8          # ±۸ سال
COMPARABLE_MAX = 6

#: وزن هر ویژگی در فاصلهٔ شباهت — متراژ و سن مهم‌ترین‌اند.
_SIMILARITY_WEIGHTS = {
    "area": 1.0, "age": 0.55, "bedrooms": 0.35, "floor": 0.2,
}
_BOOLEAN_FEATURES = ("parking", "storage", "elevator")
_BINARY_MAJORITY = 0.5


@dataclass(frozen=True)
class FactorEffect:
    """سهم یک ویژگی در قیمت پیش‌بینی‌شده."""

    feature: str
    label: str
    value_label: str
    amount: int

    @property
    def is_positive(self) -> bool:
        return self.amount > 0


@dataclass(frozen=True)
class ComparableSet:
    """ملک‌های مشابه و آماره‌هایشان."""

    items: tuple[Listing, ...]
    median_price: int
    median_price_per_m2: int
    count: int

    @property
    def is_empty(self) -> bool:
        return not self.items


@dataclass(frozen=True)
class Explanation:
    """همهٔ چیزهایی که صفحهٔ پیش‌بینی نشان می‌دهد."""

    price: int
    low: int
    high: int
    price_per_m2: int
    base_price: int
    factors: tuple[FactorEffect, ...]
    #: اختلاف باقی‌مانده از گرد کردن سهم‌ها — در حالت درست صفر است.
    residual: int
    comparables: ComparableSet

    @property
    def interval_width(self) -> int:
        return self.high - self.low

    @property
    def relative_width(self) -> float:
        return self.interval_width / self.price if self.price else 0.0

    def comparable_gap(self) -> float | None:
        """اختلاف مدل با میانهٔ ملک‌های مشابه — نسبی."""
        if self.comparables.is_empty or not self.comparables.median_price:
            return None
        return (self.price - self.comparables.median_price) / self.comparables.median_price


@functools.lru_cache(maxsize=1)
def reference_property() -> dict:
    """ملک مرجع — میانهٔ عددی‌ها و حالت دسته‌ای‌ها در دیتاست.

    سهم ویژگی‌ها نسبت به این نقطه سنجیده می‌شود، پس «پایه» یک ملک معمولی
    شهر است، نه یک ملک ساختگی با مقدار صفر.
    """
    frame = get_dataset()
    reference: dict[str, float | int] = {}
    for name in FEATURES:
        column = frame[name]
        reference[name] = (int(column.mode().iloc[0]) if name in _BOOLEAN_FEATURES
                           or name in ("district", "bedrooms")
                           else int(round(float(column.median()))))
    # منطقهٔ مرجع «میانهٔ ضریب» است نه پرتکرارترین کد، تا مقایسه با کل شهر منصفانه باشد.
    reference["district"] = int(frame.groupby("district")["price"].median().index[
        len(frame.groupby("district")["price"].median()) // 2])
    return reference


@functools.lru_cache(maxsize=1)
def attribution_orders() -> tuple[tuple[str, ...], ...]:
    """ترتیب‌های مورد استفاده در تقسیم سهم‌ها.

    ترتیب اصلی همان ترتیب اعلامی ویژگی‌هاست (تکرار‌شدنی و قابل استناد) و
    بقیه با seed ثابت تولید می‌شوند تا نتیجه بین اجراها تفاوت نکند.
    """
    rng = np.random.default_rng(RANDOM_SEED)
    orders: list[tuple[str, ...]] = [tuple(FEATURES)]
    for _ in range(max(0, ATTRIBUTION_ORDERS - 1)):
        shuffled = list(FEATURES)
        rng.shuffle(shuffled)
        orders.append(tuple(shuffled))
    return tuple(orders)


def factor_effects(bundle: dict, features: dict) -> tuple[tuple[FactorEffect, ...], int, int]:
    """سهم هر ویژگی + قیمت پایه + باقی‌ماندهٔ گردکردن.

    برای هر ترتیب، از ملک مرجع آغاز می‌کنیم و ویژگی‌ها را یکی‌یکی وارد می‌کنیم.
    چون در هر ترتیب مجموع گام‌ها برابر کل تغییر قیمت است، میانگین گرفتن از
    سهم‌ها هم این ویژگی را حفظ می‌کند و «اثر متقابلِ» بی‌توضیح باقی نمی‌ماند.
    """
    reference = reference_property()
    base_price = predict(bundle, reference)
    full_price = predict(bundle, features)

    totals = {name: 0.0 for name in FEATURES}
    orders = attribution_orders()
    for order in orders:
        current = dict(reference)
        previous = base_price
        for name in order:
            current[name] = features[name]
            price = predict(bundle, current)
            totals[name] += price - previous
            previous = price

    effects = [
        FactorEffect(
            feature=name,
            label=feature_delta_label(name, totals[name]),
            value_label=feature_value_label(name, features[name]),
            amount=int(round(totals[name] / len(orders))),
        )
        for name in FEATURES
    ]
    effects.sort(key=lambda item: -abs(item.amount))
    residual = int(full_price - base_price - sum(item.amount for item in effects))
    return tuple(effects), int(base_price), residual


def _similarity_distance(row: pd.Series, target: dict) -> float:
    """فاصلهٔ وزنی نرمال‌شده — کوچک‌تر یعنی شبیه‌تر."""
    total = 0.0
    for name, weight in _SIMILARITY_WEIGHTS.items():
        scale = max(1.0, abs(float(target[name])) * 0.5)
        total += weight * (abs(float(row[name]) - float(target[name])) / scale) ** 2
    # نبودِ هر امکانات، جریمهٔ کوچکی دارد تا ملک‌های هم‌ویژگی بالاتر بیایند.
    for name in _BOOLEAN_FEATURES:
        if int(row[name]) != int(target[name]):
            total += 0.05
    return float(np.sqrt(total))


def find_comparables(features: dict, *, limit: int = COMPARABLE_MAX) -> ComparableSet:
    """نزدیک‌ترین آگهی‌های همان منطقه به این مشخصات."""
    frame = pd.DataFrame([{
        "id": item.id, "district": item.district, "area": item.area,
        "bedrooms": item.bedrooms, "age": item.age, "floor": item.floor,
        "parking": item.parking, "storage": item.storage, "elevator": item.elevator,
        "price": item.price, "price_per_m2": item.price_per_m2,
    } for item in all_listings()])

    candidates = frame[frame["district"] == int(features["district"])].copy()
    if candidates.empty:
        candidates = frame.copy()

    area = float(features["area"])
    age = float(features["age"])
    candidates = candidates[
        candidates["area"].between(area * (1 - COMPARABLE_AREA_TOLERANCE),
                                   area * (1 + COMPARABLE_AREA_TOLERANCE))
        & candidates["age"].between(age - COMPARABLE_AGE_TOLERANCE,
                                    age + COMPARABLE_AGE_TOLERANCE)]

    if candidates.empty:
        # دامنه را باز می‌کنیم ولی همان معیار شباهت را نگه می‌داریم؛ بهتر از
        # برگرداندن فهرست خالی یا فروختن ملک بی‌ربط به‌عنوان «مشابه» است.
        candidates = frame[frame["district"] == int(features["district"])].copy()

    candidates["_distance"] = candidates.apply(
        lambda row: _similarity_distance(row, features), axis=1)
    candidates = candidates.sort_values("_distance").head(limit)

    lookup = {item.id: item for item in all_listings()}
    items = tuple(lookup[row["id"]] for _, row in candidates.iterrows())
    return ComparableSet(
        items=items,
        median_price=int(candidates["price"].median()) if len(candidates) else 0,
        median_price_per_m2=int(candidates["price_per_m2"].median()) if len(candidates) else 0,
        count=int(len(candidates)),
    )


def explain(bundle: dict, features: dict) -> Explanation:
    """توضیح کامل یک پیش‌بینی."""
    price = predict(bundle, features)
    low, high = predict_interval(bundle, features)
    effects, base_price, residual = factor_effects(bundle, features)
    area = int(features.get("area") or 0)
    return Explanation(
        price=price,
        low=low,
        high=high,
        price_per_m2=int(price / area) if area else 0,
        base_price=base_price,
        factors=effects,
        residual=residual,
        comparables=find_comparables(features),
    )


def explain_listing(bundle: dict, listing: Listing) -> Explanation:
    return explain(bundle, listing.as_features())


def factor_table(explanation: Explanation) -> pd.DataFrame:
    """جدول فارسی اثر عامل‌ها — برای نمایش و آزمون."""
    total = sum(abs(item.amount) for item in explanation.factors) or 1
    return pd.DataFrame([{
        "ویژگی": item.label,
        "مقدار": item.value_label,
        "اثر (تومان)": item.amount,
        "سهم": item.amount / total,
    } for item in explanation.factors])


def explanation_summary(explanation: Explanation) -> str:
    """یک پاراگراف فارسی که پیش‌بینی را ساده توضیح می‌دهد."""
    area = int(explanation.price_per_m2)
    rising = [item for item in explanation.factors if item.amount > 0][:2]
    falling = [item for item in explanation.factors if item.amount < 0][:2]
    parts = [
        f"مدل برای این مشخصات {fa_number(explanation.price)} تومان پیش‌بینی می‌کند "
        f"({fa_number(area)} تومان در هر مترمربع).",
    ]
    if rising:
        parts.append("بیشترین افزایش از " + " و ".join(
            f"{item.label}" for item in rising) + " می‌آید.")
    if falling:
        parts.append("کاهنده‌ترین عامل " + " و ".join(
            f"{item.label}" for item in falling) + " است.")
    if not explanation.comparables.is_empty:
        gap = explanation.comparable_gap()
        if gap is not None:
            direction = "بالاتر" if gap > 0 else "پایین‌تر"
            parts.append(
                f"این عدد نسبت به میانهٔ {fa_number(explanation.comparables.count)} "
                f"ملک مشابه {fa_number(abs(gap) * 100, decimals=1)}٪ {direction} است.")
    return " ".join(parts)
