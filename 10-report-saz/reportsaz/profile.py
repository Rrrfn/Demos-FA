# -*- coding: utf-8 -*-
"""پروفایل داده — شناسایی نوع ستون‌ها، سنجش کیفیت و یافتن مقادیر مشکوک.

سه پرسش این ماژول پاسخ می‌دهد و هر سه در رابط دیده می‌شوند:

۱) **هر ستون چه نوعی است؟** عدد، متن، تاریخ یا شناسه. پاسخ روی *نمونه* حساب
   می‌شود، نه کل فایل — تشخیص نوع با ۶ هزار سطر اول همان نتیجهٔ کل فایل را
   می‌دهد و روی فایل بزرگ چند برابر سریع‌تر است. نسبت لازم برای پذیرش یک نوع
   در ``TYPE_PASS_RATIO`` است؛ ستونی که ۸۰٪ عدد است عدد شمرده نمی‌شود، چون
   ستون عدد نامیده شود ولی ۲۰٪ متن داشته باشد، هر جمعی روی آن غلط است.

۲) **کیفیت داده چقدر است؟** امتیاز از چهار زیرامتیاز ساخته می‌شود و وزن‌ها در
   ``config.QUALITY_WEIGHTS`` اعلام شده‌اند. روش کار در رابط، PDF و README
   از یک رشتهٔ واحد (``config.QUALITY_METHOD``) می‌آید تا هر سه یک چیز بگویند.

۳) **چه چیزی مشکوک است؟** مقدار پرت، تاریخ خارج از بازه، متن در ستون عددی،
   و ستون‌هایی با یک مقدار تکراری. فهرست مشکوک‌ها *پیشنهاد* است نه حکم؛ کاربر
   تصمیم می‌گیرد و هیچ‌چیز بی‌اجازهٔ او عوض نمی‌شود.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import (CUSTOMER_HINTS, DATE_HINTS, DIMENSION_BUSY_UNIQUE,
                     DIMENSION_MAX_UNIQUE, DIMENSION_MIN_UNIQUE, ID_HINTS,
                     ID_UNIQUE_RATIO, METRIC_HINTS, PRODUCT_HINTS,
                     QUALITY_BANDS, QUALITY_WEIGHTS, REGION_HINTS,
                     TYPE_SAMPLE_ROWS, TYPE_PASS_RATIO)
from .ingest.cells import clean_text, parse_date, parse_number, plausible_date
from .labels import fa_number, fa_percent

#: نقش‌های ممکن یک ستون در تحلیل.
ROLE_METRIC = "metric"
ROLE_DIMENSION = "dimension"
ROLE_DATE = "date"
ROLE_IDENTIFIER = "identifier"
ROLE_TEXT = "text"

TYPE_NUMBER = "number"
TYPE_TEXT = "text"
TYPE_DATE = "date"
TYPE_BOOLEAN = "boolean"

#: برچسب فارسی نقش‌ها — یک منبع حقیقت برای رابط و گزارش.
ROLE_LABELS = {
    ROLE_METRIC: "متریک",
    ROLE_DIMENSION: "بعد",
    ROLE_DATE: "تاریخ",
    ROLE_IDENTIFIER: "شناسه",
    ROLE_TEXT: "متن",
}

TYPE_LABELS = {
    TYPE_NUMBER: "عدد",
    TYPE_TEXT: "متن",
    TYPE_DATE: "تاریخ",
    TYPE_BOOLEAN: "بولی",
}


@dataclass
class ColumnProfile:
    """شناسنامهٔ یک ستون."""

    name: str
    position: int
    dtype: str
    type: str
    role: str
    missing: int
    unique: int
    filled: int = 0
    #: نسبت مقادیری که با نوع تشخیص‌داده‌شده می‌خوانند.
    validity: float = 1.0
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    #: مجموع — برای متریک‌های جمع‌شونده.
    total: float | None = None
    #: رایج‌ترین مقدار و سهمش.
    top_value: str = ""
    top_share: float = 0.0
    #: تاریخ‌های معتبر وقتی نوع، تاریخ است.
    date_min: str = ""
    date_max: str = ""
    #: مقادیر مشکوک این ستون.
    suspicious: list[dict] = field(default_factory=list)
    #: قالب‌های نمایش متفاوت دیده‌شده در ستون (برای زیرامتیاز یکدستی).
    formats: int = 1

    @property
    def fill_ratio(self) -> float:
        return 0.0 if not (self.filled + self.missing) else \
            self.filled / (self.filled + self.missing)

    @property
    def type_label(self) -> str:
        return TYPE_LABELS.get(self.type, self.type)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "position": self.position,
            "dtype": self.dtype,
            "type": self.type,
            "type_label": self.type_label,
            "role": self.role,
            "role_label": self.role_label,
            "missing": self.missing,
            "unique": self.unique,
            "filled": self.filled,
            "validity": self.validity,
            "fill_ratio": self.fill_ratio,
            "min": self.minimum,
            "max": self.maximum,
            "mean": self.mean,
            "median": self.median,
            "std": self.std,
            "total": self.total,
            "top_value": self.top_value,
            "top_share": self.top_share,
            "date_min": self.date_min,
            "date_max": self.date_max,
            "formats": self.formats,
            "suspicious": list(self.suspicious),
            "suspicious_count": len(self.suspicious),
        }


@dataclass
class Profile:
    """پروفایل کامل یک جدول."""

    rows: int
    columns: int
    cells: int
    missing: int
    duplicates: int
    columns_profile: list[ColumnProfile] = field(default_factory=list)
    quality: dict = field(default_factory=dict)
    suspicious_total: int = 0
    notes: list[str] = field(default_factory=list)

    def by_name(self, name: str) -> ColumnProfile | None:
        for column in self.columns_profile:
            if column.name == name:
                return column
        return None

    def role(self, name: str) -> str:
        column = self.by_name(name)
        return column.role if column else ROLE_TEXT

    def metrics(self) -> list[ColumnProfile]:
        return [c for c in self.columns_profile if c.role == ROLE_METRIC]

    def dimensions(self) -> list[ColumnProfile]:
        return [c for c in self.columns_profile if c.role == ROLE_DIMENSION]

    def dates(self) -> list[ColumnProfile]:
        return [c for c in self.columns_profile if c.role == ROLE_DATE]

    def date_column(self) -> ColumnProfile | None:
        dates = self.dates()
        if not dates:
            return None
        #: ستونی که نامش نشانهٔ تاریخ دارد اولویت دارد، وگرنه پرترین.
        for column in dates:
            if _matches(column.name, DATE_HINTS):
                return column
        return max(dates, key=lambda column: column.filled)

    def as_dict(self) -> dict:
        return {
            "rows": self.rows,
            "columns": self.columns,
            "cells": self.cells,
            "missing": self.missing,
            "duplicates": self.duplicates,
            "quality": dict(self.quality),
            "suspicious_total": self.suspicious_total,
            "notes": list(self.notes),
            "columns_profile": [c.as_dict() for c in self.columns_profile],
        }


def _matches(name: str, hints: tuple[str, ...]) -> bool:
    lowered = str(name).strip().lower()
    return any(hint in lowered for hint in hints)


# ------------------------------------------------------------------ نوع ستون
def infer_type(series: pd.Series) -> tuple[str, float, int]:
    """نوع غالب ستون با نسبت اعتبار.

    خروجی: ``(نوع, نسبت اعتبار, شمار قالب‌های متفاوت)``. نسبت اعتبار یعنی چند
    درصد مقادیر غیرخالی با آن نوع می‌خوانند — همان عددی که به کاربر نشان داده
    می‌شود تا بداند ستون «عدد» چقدر واقعاً عدد است.
    """
    values = series.dropna()
    if values.empty:
        return TYPE_TEXT, 1.0, 1

    numbers = sum(1 for value in values if parse_number(value) is not None)
    dates = sum(1 for value in values if parse_date(value) is not None)
    bools = 0
    for value in values:
        lowered = clean_text(value).lower()
        if lowered in {"true", "false", "yes", "no", "بله", "خیر", "آری", "نه"}:
            bools += 1

    total = len(values)
    formats = _format_variety(values)
    if total == 0:
        return TYPE_TEXT, 1.0, formats

    #: ترتیب بررسی مهم است: تاریخ پیش از عدد می‌آید چون «۲۰۲۴۰۳۰۱» هم عدد
    #: خوانده می‌شود، ولی ستونی که بیشترش تاریخ است باید تاریخ بماند.
    for kind, hits in ((TYPE_BOOLEAN, bools), (TYPE_DATE, dates),
                       (TYPE_NUMBER, numbers)):
        ratio = hits / total
        if ratio >= TYPE_PASS_RATIO:
            return kind, ratio, formats
    return TYPE_TEXT, 1.0, formats


def _format_variety(values: pd.Series) -> int:
    """شمار قالب‌های نمایش متفاوت در مقدارهای یک ستون.

    «۱٬۲۰۰» و «1200» و «۱٬۲۰۰٫۰۰» سه قالب مختلف یک عددند. ستونی که عددش را
    سه شکل می‌نویسد، یکدست نیست و امتیاز کیفیت کمتری می‌گیرد. سنجش روی ۵۰۰
    مقدار اول انجام می‌شود چون هدف تشخیص *تنوع شکل* است، نه شمارش دقیق.
    """
    seen: set[str] = set()
    for value in list(values)[:500]:
        text = clean_text(value)
        if not text:
            continue
        shape = []
        for char in text:
            if char.isdigit():
                shape.append("d")
            elif char in ".,٬٫":
                shape.append("s")
            elif char in "ریال تومان د $€£":
                shape.append("c")
            elif char.isalpha():
                shape.append("a")
        seen.add("".join(shape)[:24])
        if len(seen) > 6:
            break
    return max(1, len(seen))


def _suspicious(series: pd.Series, column_type: str,
                values: pd.Series) -> list[dict]:
    """مقادیر مشکوک ستون — با *دلیل* هر مورد، نه فقط شمارش."""
    found: list[dict] = []
    filled = max(1, int(values.notna().sum()))

    if column_type == TYPE_NUMBER:
        parsed = pd.to_numeric(values.map(parse_number), errors="coerce").dropna()
        if len(parsed) >= 4:
            low, high = parsed.quantile(0.25), parsed.quantile(0.75)
            spread = float(high - low)
            if spread > 0:
                lower, upper = float(low) - 1.5 * spread, float(high) + 1.5 * spread
                outliers = int(((parsed < lower) | (parsed > upper)).sum())
                if outliers:
                    found.append({
                        "kind": "outlier",
                        "count": outliers,
                        "ratio": outliers / filled,
                        "reason": "مقدار دور از بازهٔ معمول ستون (روش IQR)",
                    })
        negatives = int((parsed < 0).sum())
        if negatives:
            found.append({
                "kind": "negative",
                "count": negatives,
                "ratio": negatives / filled,
                "reason": "مقدار منفی؛ اگر ستون جمع‌شونده است (مثل مبلغ یا تعداد) "
                          "منفی بودن آن را بررسی کنید",
            })
        #: متنی که شبیه عدد است ولی با نوع نمی‌خواند.
        failed = int(values.map(lambda value: value is not None
                                and clean_text(value) != ""
                                and parse_number(value) is None).sum())
        if failed:
            found.append({
                "kind": "non_numeric",
                "count": failed,
                "ratio": failed / filled,
                "reason": "سلول غیرعددی در ستونی که عمدتاً عدد است",
            })
    elif column_type == TYPE_DATE:
        bad = int(values.map(lambda value: parse_date(value) is not None
                             and not plausible_date(parse_date(value))).sum())
        if bad:
            found.append({
                "kind": "implausible_date",
                "count": bad,
                "ratio": bad / filled,
                "reason": "تاریخ خارج از بازهٔ معقول (سال ۱۹۹۰ تا ۲۱۰۰)",
            })
        unparsed = int(values.map(lambda value: clean_text(value) != ""
                                  and parse_date(value) is None).sum())
        if unparsed:
            found.append({
                "kind": "unparsed_date",
                "count": unparsed,
                "ratio": unparsed / filled,
                "reason": "مقداری که به‌عنوان تاریخ خوانده نشد",
            })
    else:
        blanks = int(values.map(lambda value: str(value) != ""
                                and clean_text(value) == "").sum())
        if blanks:
            found.append({
                "kind": "blank_variant",
                "count": blanks,
                "ratio": blanks / filled,
                "reason": "سلول پر از فاصله یا نویسهٔ نامرئی",
            })

    return found


def _role(name: str, column_type: str, unique: int, rows: int,
          numbers: int, values: pd.Series) -> str:
    """نقش ستون در تحلیل — متریک، بعد، تاریخ، شناسه یا متن."""
    lowered = str(name).strip().lower()
    if column_type == TYPE_DATE:
        return ROLE_DATE
    if unique <= 1:
        return ROLE_TEXT
    if column_type == TYPE_NUMBER:
        #: ستونی که تقریباً همهٔ مقدارهایش یکتاست، *کاندیدای* شناسه است — ولی
        #: یکتایی تنها کافی نیست: در جدول ده‌سطری، هر متریکی هم ده مقدار یکتا
        #: دارد. حکم شناسه وقتی صادر می‌شود که نام ستون هم نشانهٔ شناسه داشته
        #: باشد، یا نام هیچ نشانهٔ متریکی نداشته باشد و مقدارها شکل شناسه
        #: داشته باشند (صحیح متوالی). جمع‌زدن شناسه در گزارش بی‌معناست.
        distinct = rows > 0 and (unique / max(1, numbers)) >= ID_UNIQUE_RATIO
        if distinct and _matches(lowered, ID_HINTS):
            return ROLE_IDENTIFIER
        metric_hint = _matches(lowered, METRIC_HINTS)
        if distinct and not metric_hint and _looks_sequential(values):
            return ROLE_IDENTIFIER
        return ROLE_METRIC
    #: متن: اگر شمار مقدار یکتا در بازهٔ معقول باشد، بعد تحلیلی است.
    if DIMENSION_MIN_UNIQUE <= unique <= DIMENSION_BUSY_UNIQUE:
        if _matches(lowered, DATE_HINTS):
            return ROLE_TEXT
        return ROLE_DIMENSION
    return ROLE_TEXT


def _looks_sequential(values: pd.Series) -> bool:
    """آیا ستون شمارندهٔ یکنواخت است؟ نشانهٔ شناسهٔ تولیدشده، نه متریک.

    معیار: همهٔ مقدارها عدد صحیح، و بازه دقیقاً برابر شمار مقدارهای یکتا — یعنی
    از ۱ تا n بدون پرش. مبلغ فروش این‌طور نیست، شمارهٔ ردیف است.
    """
    parsed = [parse_number(value) for value in values]
    numbers = [number for number in parsed
               if number is not None and float(number).is_integer()]
    if len(numbers) < 4 or len(numbers) != len(parsed):
        return False
    distinct = sorted(set(numbers))
    if len(distinct) != len(numbers):
        return False
    return (distinct[-1] - distinct[0]) == len(distinct) - 1 and distinct[0] in (0, 1)


def _dimension_score(name: str, column: ColumnProfile) -> float:
    """امتیاز «بعد بودن» — برای انتخاب بعد پیش‌فرض نمودارها.

    نام‌های آشنا (منطقه، محصول، مشتری) امتیاز بیشتری می‌گیرند و تعداد یکتا در
    بازهٔ خوانا امتیاز کامل. بعدی که ۴۰۰ مقدار یکتا دارد برای نمودار بی‌فایده
    است، هرچند بعد باشد.
    """
    score = 0.0
    if REGION_HINTS and _matches(name, REGION_HINTS):
        score += 2.0
    if _matches(name, PRODUCT_HINTS):
        score += 1.8
    if _matches(name, CUSTOMER_HINTS):
        score += 1.4
    unique = column.unique
    if 3 <= unique <= DIMENSION_MAX_UNIQUE:
        score += 2.0
    elif DIMENSION_MAX_UNIQUE < unique <= DIMENSION_BUSY_UNIQUE:
        score += 1.0
    elif unique == 2:
        score += 0.8
    score += min(1.0, column.fill_ratio)
    return score


def _metric_score(name: str, column: ColumnProfile) -> float:
    """امتیاز «متریک بودن» — مبلغ و تعداد بر سایر عددها مقدم‌اند."""
    score = 0.0
    if _matches(name, METRIC_HINTS):
        score += 2.5
    if column.total not in (None, 0):
        score += 0.8
    if column.mean is not None and column.std is not None and column.mean != 0:
        #: ضریب تغییرات: متریکی که همه مقدارهایش یکی است (واریانس صفر) برای
        #: تحلیل جذاب نیست.
        variation = abs(column.std / column.mean)
        score += min(1.2, variation)
    score += min(1.0, column.fill_ratio)
    return score


# ------------------------------------------------------------------ امتیاز کیفیت
def quality_score(profile_rows: int, cells: int, missing: int, duplicates: int,
                  columns: list[ColumnProfile]) -> dict:
    """امتیاز کیفیت از چهار زیرامتیاز وزن‌دار (وزن‌ها در config اعلام شده‌اند)."""
    completeness = 1.0 if cells == 0 else max(0.0, 1 - missing / cells)
    validity = (sum(c.validity * c.filled for c in columns) /
                max(1, sum(c.filled for c in columns))) if columns else 1.0
    uniqueness = 1.0 if profile_rows == 0 else \
        max(0.0, 1 - duplicates / profile_rows)
    consistency = (sum(1.0 if column.formats <= 1 else 1.0 / column.formats
                       for column in columns) / len(columns)) if columns else 1.0

    parts = {
        "completeness": round(completeness * 100, 1),
        "validity": round(validity * 100, 1),
        "uniqueness": round(uniqueness * 100, 1),
        "consistency": round(consistency * 100, 1),
    }
    score = sum(parts[key] * weight for key, weight in QUALITY_WEIGHTS.items())
    score = round(max(0.0, min(100.0, score)), 1)
    label = next(label for threshold, label in QUALITY_BANDS if score >= threshold)
    return {"score": score, "label": label, "parts": parts}


def profile_frame(frame: pd.DataFrame) -> Profile:
    """پروفایل کامل یک جدول — از سرصفحه تا امتیاز کیفیت."""
    rows, columns = frame.shape
    cells = int(rows * columns)
    missing = int(frame.isna().sum().sum())
    duplicates = int(frame.duplicated().sum())

    profiles: list[ColumnProfile] = []
    sample = frame.head(TYPE_SAMPLE_ROWS)
    for position, name in enumerate(frame.columns, start=1):
        column = sample[name]
        column_type, validity, formats = infer_type(column)
        values = column.dropna()
        unique = int(frame[name].nunique(dropna=True))
        numbers = int(values.map(parse_number).notna().sum())

        entry = ColumnProfile(
            name=str(name), position=position, dtype=str(frame[name].dtype),
            type=column_type, role=ROLE_TEXT,
            missing=int(frame[name].isna().sum()), unique=unique,
            filled=int(len(values)), validity=round(validity, 4), formats=formats,
        )
        entry.role = _role(str(name), column_type, unique, rows, numbers, values)

        if column_type == TYPE_NUMBER:
            parsed = pd.to_numeric(values.map(parse_number), errors="coerce").dropna()
            if len(parsed):
                entry.minimum = float(parsed.min())
                entry.maximum = float(parsed.max())
                entry.mean = float(parsed.mean())
                entry.median = float(parsed.median())
                entry.std = float(parsed.std()) if len(parsed) > 1 else 0.0
                entry.total = float(parsed.sum())
        if column_type == TYPE_DATE:
            parsed_dates = [parse_date(value) for value in values]
            valid = sorted(date for date in parsed_dates
                           if date is not None and plausible_date(date))
            if valid:
                entry.date_min = valid[0].isoformat()
                entry.date_max = valid[-1].isoformat()

        if entry.role in (ROLE_DIMENSION, ROLE_TEXT) and len(values):
            counts = values.astype(str).map(clean_text).value_counts()
            if len(counts):
                entry.top_value = str(counts.index[0])[:60]
                entry.top_share = float(counts.iloc[0] / max(1, len(values)))

        entry.suspicious = _suspicious(frame[name], column_type, values)
        profiles.append(entry)

    quality = quality_score(rows, cells, missing, duplicates, profiles)
    notes: list[str] = []
    if duplicates:
        notes.append(f"{fa_number(duplicates)} ردیف کاملاً تکراری در جدول هست.")
    if missing:
        notes.append(f"{fa_number(missing)} سلول خالی در جدول هست "
                     f"({fa_percent(missing / max(1, cells))} از کل).")
    suspicious_total = sum(len(column.suspicious) for column in profiles)
    if suspicious_total:
        notes.append(f"در {fa_number(suspicious_total)} مورد مقدار مشکوک دیده شد؛ "
                     "فهرست کامل در بخش بازرسی آمده است.")

    return Profile(
        rows=int(rows), columns=int(columns), cells=cells, missing=missing,
        duplicates=duplicates, columns_profile=profiles, quality=quality,
        suspicious_total=suspicious_total, notes=notes,
    )


def pick_dimensions(profile: Profile, limit: int = 6) -> list[str]:
    """بعدهای پیشنهادی برای نمودارها، به ترتیب امتیاز."""
    candidates = profile.dimensions()
    scored = [(column.name, _dimension_score(column.name, column))
              for column in candidates]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [name for name, _ in scored[:limit]]


def pick_metrics(profile: Profile, limit: int = 4) -> list[str]:
    """متریک‌های پیشنهادی برای کارت‌های شاخص و نمودارها."""
    scored = [(column.name, _metric_score(column.name, column))
              for column in profile.metrics()]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [name for name, _ in scored[:limit]]
