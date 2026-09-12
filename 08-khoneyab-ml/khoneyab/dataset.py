# -*- coding: utf-8 -*-
"""تولید دیتاست سینتتیک مسکن تهران.

**هشدار مهم:** این داده ساختگی است. هیچ رکوردی از آگهی واقعی گرفته نشده و
قیمت‌ها قیمت واقعی بازار نیستند. هدف، ساختن مجموعه‌ای است که *ساختار* بازار
را داشته باشد تا مدل بتواند آن ساختار را از دل داده کشف کند:

    قیمت‌متر = پایه × ضریب منطقه
              × (۱ + پارکینگ + انباری + آسانسور + اتاق خواب)
              × استهلاک سن × ضریب طبقه × نوسان تصادفی

چون سازوکار تولید داده صریح است، می‌دانیم مدل *باید* به چه نتیجه‌ای برسد؛
اگر مدل رفتار عجیبی نشان دهد، ایراد از مدل است نه از داده.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .config import (AGE_RANGE, ANNUAL_DEPRECIATION, AREA_RANGE, BASE_PRICE_M2,
                     BASEMENT_FACTOR, BEDROOM_PREMIUM, BEDROOM_RANGE,
                     DEPRECIATION_CAP_YEARS, ELEVATOR_PREMIUM, FEATURES,
                     FLOOR_PREMIUM_CAP, FLOOR_PREMIUM_PER_LEVEL, FLOOR_RANGE,
                     GROUND_FACTOR, N_SAMPLES, PARKING_PREMIUM,
                     PRICE_NOISE_SIGMA, RANDOM_SEED, STORAGE_PREMIUM, TARGET,
                     dataset_path, district_factor)

#: نویسی که باعث می‌شود تعداد اتاق کاملاً تابعی از متراژ نباشد.
_BEDROOM_NOISE = 0.6
_METERS_PER_BEDROOM = 40.0


def _floor_factor(floor: np.ndarray) -> np.ndarray:
    """همکف و زیرزمین ارزان‌تر، طبقات بالاتر تا سقف گران‌تر."""
    mid_and_up = 1.0 + np.minimum(floor, FLOOR_PREMIUM_CAP) * FLOOR_PREMIUM_PER_LEVEL
    return np.where(floor < 0, BASEMENT_FACTOR,
                    np.where(floor == 0, GROUND_FACTOR, mid_and_up))


def generate(n: int = N_SAMPLES, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """ساخت ``n`` رکورد ملک مسکونی.

    خروجی ستون‌هایی دقیقاً مطابق ``config.FEATURES`` به‌علاوهٔ ``price`` دارد و
    با seed ثابت همیشه یکسان است — پس آزمون‌ها و نمودارهای README تکرارپذیرند.
    """
    if n <= 0:
        raise ValueError("تعداد نمونه باید مثبت باشد")
    rng = np.random.default_rng(seed)

    district = rng.integers(1, 23, n)
    area = np.clip(rng.gamma(shape=6.0, scale=16.0, size=n), *AREA_RANGE).round(0)
    bedrooms = np.clip(
        np.round(area / _METERS_PER_BEDROOM + rng.normal(0.0, _BEDROOM_NOISE, n)),
        *BEDROOM_RANGE).astype(int)
    age = np.clip(rng.gamma(shape=2.2, scale=6.5, size=n), *AGE_RANGE).round(0).astype(int)
    floor = np.clip(rng.integers(FLOOR_RANGE[0], FLOOR_RANGE[1] + 1, n), *FLOOR_RANGE).astype(int)

    factors = np.array([district_factor(int(code)) for code in district])

    # امکانات با منطقه و طبقه همبستگی دارند — مثل واقعیت: ساختمان‌های نوسازِ
    # شمال شهر آسانسور و پارکینگ بیشتری دارند.
    parking = rng.random(n) < np.clip(0.30 + 0.16 * factors, 0.0, 1.0)
    storage = rng.random(n) < 0.55
    elevator = (floor >= 2) & (rng.random(n) < 0.82)

    price_m2 = (
        BASE_PRICE_M2
        * factors
        * (1.0 + parking * PARKING_PREMIUM + storage * STORAGE_PREMIUM
           + elevator * ELEVATOR_PREMIUM + bedrooms * BEDROOM_PREMIUM)
        * (1.0 - np.minimum(age, DEPRECIATION_CAP_YEARS) * ANNUAL_DEPRECIATION)
        * _floor_factor(floor)
        * rng.normal(1.0, PRICE_NOISE_SIGMA, n)
    )
    price = (price_m2 * area).round(-6)          # رُند به میلیون تومان

    frame = pd.DataFrame({
        "district": district.astype(int),
        "area": area.astype(int),
        "bedrooms": bedrooms,
        "age": age,
        "floor": floor,
        "parking": parking.astype(int),
        "storage": storage.astype(int),
        "elevator": elevator.astype(int),
        TARGET: price.astype("int64"),
    })
    return frame[list(FEATURES) + [TARGET]]


def get_dataset(force: bool = False) -> pd.DataFrame:
    """خواندن دیتاست از دیسک؛ در نبود فایل، تولید و ذخیره می‌کند."""
    path = dataset_path()
    if force or not os.path.exists(path):
        frame = generate()
        frame.to_csv(path, index=False)
        return frame
    return pd.read_csv(path)
