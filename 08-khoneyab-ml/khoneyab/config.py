# -*- coding: utf-8 -*-
"""پیکربندی خانه‌یاب — مسیرها، مناطق تهران و پارامترهای مدل قیمت.

این ماژول «یک منبع حقیقت» برای چیزهایی است که هم مدل و هم رابط به آن‌ها نیاز
دارند: فهرست ۲۲ منطقهٔ شهرداری تهران با نام محله‌ها و ضریب قیمت، بازهٔ مجاز هر
ویژگی، و مسیر فایل‌ها. هیچ‌جای دیگری نباید ضریب منطقه یا بازهٔ متراژ را از نو
تعریف کند؛ وگرنه فرم جست‌وجو و مدل می‌توانند از هم جدا بیفتند.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")
STATIC_DIR = os.path.join(BASE_DIR, "static")
PHOTO_DIR = os.path.join(STATIC_DIR, "img", "properties")

for _path in (DATA_DIR, MODELS_DIR, PHOTO_DIR):
    os.makedirs(_path, exist_ok=True)

# ---------------------------------------------------------------- تکرارپذیری
RANDOM_SEED = 42
N_SAMPLES = 6000          # حجم دیتاست آموزش
N_LISTINGS = 900          # تعداد آگهی‌های قابل مرور در بخش جست‌وجو
TEST_SIZE = 0.2
CV_FOLDS = 5

# ---------------------------------------------------------------- ویژگی‌ها
FEATURES = ("district", "area", "bedrooms", "age", "floor",
            "parking", "storage", "elevator")
TARGET = "price"

NUMERIC_FEATURES = ("area", "bedrooms", "age", "floor")
CATEGORICAL_FEATURES = ("district", "parking", "storage", "elevator")

AREA_RANGE = (40, 400)
BEDROOM_RANGE = (0, 5)
AGE_RANGE = (0, 45)
FLOOR_RANGE = (-1, 15)
PRICE_RANGE_M2 = (40_000_000, 400_000_000)

# ---------------------------------------------------------------- مدل قیمت
#: قیمت هر مترمربع برای منطقه‌ای با ضریب ۱٫۰ (تومان). مبنای تولید دیتاست
#: سینتتیک است و *قیمت واقعی بازار نیست*.
BASE_PRICE_M2 = 95_000_000
PARKING_PREMIUM = 0.07
STORAGE_PREMIUM = 0.02
ELEVATOR_PREMIUM = 0.03
BEDROOM_PREMIUM = 0.015       # اثر مستقل اتاق، جدا از اثر متراژ
ANNUAL_DEPRECIATION = 0.012
DEPRECIATION_CAP_YEARS = 35
FLOOR_PREMIUM_PER_LEVEL = 0.005
FLOOR_PREMIUM_CAP = 12
BASEMENT_FACTOR = 0.93
GROUND_FACTOR = 0.97
PRICE_NOISE_SIGMA = 0.08
LUXURY_AREA_THRESHOLD = 200   # برای دسته‌بندی «لوکس» در رابط


@dataclass(frozen=True)
class District:
    """یک منطقهٔ شهرداری تهران."""

    code: int
    name: str
    neighborhoods: tuple[str, ...]
    factor: float

    @property
    def label(self) -> str:
        return f"منطقه {to_persian_digits(self.code)} — {self.neighborhoods[0]}"


def to_persian_digits(value: object) -> str:
    """تبدیل رقم‌های لاتین به فارسی — برای نمایش در رابط."""
    table = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return str(value).translate(table)


#: ضریب هر منطقه از ساختار واقعی بازار تهران الگو گرفته: شمال شهر گران‌تر و
#: حاشیهٔ جنوبی و غربی ارزان‌تر. این ضرایب *سینتتیک* هستند.
DISTRICTS: tuple[District, ...] = (
    District(1, "شمیران", ("تجریش", "الهیه", "زعفرانیه"), 2.50),
    District(2, "سعادت‌آباد", ("شهرک غرب", "گیشا", "مرزداران"), 2.20),
    District(3, "قیطریه", ("پاسداران", "دولت", "درب دوم"), 2.35),
    District(4, "سیدخندان", ("شمس‌آباد", "حسین‌آباد", "کاج"), 1.15),
    District(5, "پونک", ("شهران", "جنت‌آباد", "آزادی"), 1.20),
    District(6, "یوسف‌آباد", ("امیرآباد", "فاطمی", "ونک"), 1.45),
    District(7, "بهارستان", ("عباس‌آباد", "هفت‌تیر", "سهروردی"), 1.10),
    District(8, "نارمک", ("تهرانپارس", "رسالت", "کرمان"), 1.00),
    District(9, "مهرآباد", ("دکتر هوشیار", "استاد معین", "آذری"), 1.05),
    District(10, "توحید", ("سلسبیل", "جی", "هاشمی"), 1.15),
    District(11, "ولیعصر", ("جمهوری", "انقلاب", "کارگر"), 1.30),
    District(12, "بازار", ("فردوسی", "بهارستان", "لاله‌زار"), 1.20),
    District(13, "پیروزی", ("نبرد", "آهنگ", "دردشت"), 0.95),
    District(14, "افسریه", ("شکوفه", "نیروی هوایی", "چهارصد دستگاه"), 0.90),
    District(15, "خزانه", ("افسریه شمالی", "مسعودیه", "ابوذر"), 0.75),
    District(16, "یافت‌آباد", ("جوادیه", "بهمنی", "نازی‌آباد"), 0.70),
    District(17, "باغ فیض", ("امامزاده عبدالله", "جوانمرد", "یافت‌آباد"), 0.75),
    District(18, "شهرک صدرا", ("شریعتی", "ولیعصر جنوبی", "مهرآباد"), 0.65),
    District(19, "نسیم‌شهر", ("اسماعیل‌آباد", "شهرک شریعتی", "دولت‌آباد"), 0.60),
    District(20, "شهرک اکباتان", ("شهرزیبا", "استاد معین", "تهرانسر"), 0.80),
    District(21, "وارش", ("تهرانسر", "شهرک دریا", "چیتگر"), 0.95),
    District(22, "چیتگر", ("البرز", "دهکده المپیک", "زیبادشت"), 1.25),
)

DISTRICT_BY_CODE: dict[int, District] = {d.code: d for d in DISTRICTS}
DISTRICT_CODES: tuple[int, ...] = tuple(d.code for d in DISTRICTS)


def district_label(code: int) -> str:
    """برچسب کوتاه منطقه برای جدول‌ها."""
    district = DISTRICT_BY_CODE.get(int(code))
    return f"منطقه {to_persian_digits(code)}" + (f" ({district.neighborhoods[0]})" if district else "")


def district_factor(code: int) -> float:
    district = DISTRICT_BY_CODE.get(int(code))
    return district.factor if district else 1.0


# ---------------------------------------------------------------- مسیرها
def dataset_path() -> str:
    return os.path.join(DATA_DIR, "housing.csv")


def model_path() -> str:
    return os.path.join(MODELS_DIR, "best_model.joblib")


def bundle_path() -> str:
    return os.path.join(MODELS_DIR, "model_bundle.joblib")


def metrics_path() -> str:
    return os.path.join(MODELS_DIR, "metrics.json")
