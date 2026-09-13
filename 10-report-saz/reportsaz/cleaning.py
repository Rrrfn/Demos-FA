# -*- coding: utf-8 -*-
"""موتور پاک‌سازی — هر تغییر، پیش از اعمال *دیده* و پس از اعمال *ثبت* می‌شود.

قاعدهٔ اصلی این ماژول: **پاک‌سازی پنهان وجود ندارد.** کاربر دو چیز می‌بیند:

* پیش از اجرا — فهرست مسائل پیداشده با شمار دقیق («۱٫۲۸۴ ردیف تکراری»).
* پس از اجرا — فهرست اصلاحات اعمال‌شده، هر کدام با شمار و شرح.

هر اصلاح از یک گزینه قابل خاموش‌کردن است. گزینه‌های پیش‌فرض محافظه‌کارانه‌اند:
آن‌چه اطلاعات را *حذف می‌کند* (ردیف تکراری) پیش‌فرض روشن است چون گزارش را
غلط می‌کند؛ آن‌چه داده را *تغییر می‌دهد* بدون درخواست کاربر (حذف پرت‌ها)
پیش‌فرض خاموش است، چون مقدار پرت ممکن است واقعی باشد.

ستون‌ها هرگز حذف نمی‌شوند مگر کاملاً خالی باشند. حذف ستونی که «بی‌فایده» به
نظر می‌رسد، دادهٔ کاربر را از تحلیل بیرون می‌برد و او نمی‌فهمد چرا.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from .ingest.cells import clean_text, parse_date, parse_number

#: شناسهٔ هر گزینهٔ پاک‌سازی — در نشانی و فرم هم همین‌ها می‌آیند.
OPT_DROP_EMPTY_ROWS = "drop_empty_rows"
OPT_DROP_DUPLICATES = "drop_duplicates"
OPT_DROP_EMPTY_COLUMNS = "drop_empty_columns"
OPT_TRIM_TEXT = "trim_text"
OPT_NUMERIC_AS_TEXT = "numeric_as_text"
OPT_NORMALIZE_NULLS = "normalize_nulls"
OPT_PARSE_DATES = "parse_dates"

#: ترتیب نمایش گزینه‌ها در رابط — همان ترتیب اعمال.
OPTION_ORDER = (
    OPT_DROP_EMPTY_ROWS, OPT_DROP_DUPLICATES, OPT_DROP_EMPTY_COLUMNS,
    OPT_TRIM_TEXT, OPT_NUMERIC_AS_TEXT, OPT_PARSE_DATES, OPT_NORMALIZE_NULLS,
)

#: گزینه‌های پیش‌فرض روشن. «حذف پرت» عمداً اینجا نیست.
DEFAULT_ON = {key: True for key in OPTION_ORDER}


@dataclass
class CleanOptions:
    """کدام اصلاح‌ها اجرا شوند."""

    flags: dict = field(default_factory=lambda: dict(DEFAULT_ON))

    @classmethod
    def from_payload(cls, payload: dict | None) -> "CleanOptions":
        """از دادهٔ فرم — هر کلید غایب یعنی روشن (پیش‌فرض)."""
        payload = payload or {}
        return cls({key: bool(payload.get(key, True)) for key in OPTION_ORDER})

    @classmethod
    def all_off(cls) -> "CleanOptions":
        return cls({key: False for key in OPTION_ORDER})

    def enabled(self, key: str) -> bool:
        return bool(self.flags.get(key, False))

    def as_dict(self) -> dict:
        return dict(self.flags)


@dataclass
class Fix:
    """یک اصلاح اعمال‌شده — همان چیزی که در «اصلاحات اعمال‌شده» دیده می‌شود."""


    key: str
    title: str
    detail: str
    affected: int
    #: آیا این اصلاح داده را از جدول بیرون برد؟
    destructive: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Finding:
    """یک مسئلهٔ پیداشده — پیش از پاک‌سازی، با شمار دقیق."""

    key: str
    title: str
    detail: str
    affected: int
    severity: str = "warning"      #: ``info`` / ``warning`` / ``critical``

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CleanResult:
    """خروجی پاک‌سازی: جدول تازه، مسائل، اصلاحات و خلاصهٔ تغییر ابعاد."""

    frame: pd.DataFrame
    findings: list[Finding] = field(default_factory=list)
    fixes: list[Fix] = field(default_factory=list)
    rows_before: int = 0
    rows_after: int = 0
    columns_before: int = 0
    columns_after: int = 0

    @property
    def rows_removed(self) -> int:
        return self.rows_before - self.rows_after

    def as_dict(self) -> dict:
        return {
            "findings": [item.as_dict() for item in self.findings],
            "fixes": [item.as_dict() for item in self.fixes],
            "rows_before": self.rows_before,
            "rows_after": self.rows_after,
            "rows_removed": self.rows_removed,
            "columns_before": self.columns_before,
            "columns_after": self.columns_after,
        }


# ------------------------------------------------------------------ تشخیص
def detect(frame: pd.DataFrame) -> list[Finding]:
    """فهرست مسائل جدول — بدون هیچ تغییری در داده."""
    findings: list[Finding] = []
    rows, columns = frame.shape

    empty_rows = int(frame.isna().all(axis=1).sum())
    if empty_rows:
        findings.append(Finding(
            OPT_DROP_EMPTY_ROWS, "ردیف کاملاً خالی",
            "ردیفی که در هیچ ستونی مقدار ندارد، نه اطلاعاتی می‌افزاید و نه "
            "در گزارش معنا دارد.",
            empty_rows, "info"))

    duplicates = int(frame.duplicated().sum())
    if duplicates:
        findings.append(Finding(
            OPT_DROP_DUPLICATES, "ردیف تکراری",
            "ردیف‌هایی که تمام مقدارهایشان با ردیف دیگری یکسان است؛ جمع و "
            "میانگین را دو برابر می‌کنند.",
            duplicates, "critical"))

    empty_columns = [str(name) for name in frame.columns
                     if frame[name].isna().all()]
    if empty_columns:
        findings.append(Finding(
            OPT_DROP_EMPTY_COLUMNS, "ستون کاملاً خالی",
            "ستونی که هیچ مقدار پرشده‌ای ندارد. نام‌ها: " +
            "، ".join(empty_columns[:6]) +
            (" و …" if len(empty_columns) > 6 else ""),
            len(empty_columns), "info"))

    padded = 0
    for name in frame.columns:
        series = frame[name]
        if series.dtype != object:
            continue
        padded += int(series.map(
            lambda value: isinstance(value, str) and value != clean_text(value)
            and clean_text(value) != "").sum())
    if padded:
        findings.append(Finding(
            OPT_TRIM_TEXT, "فاصلهٔ اضافی در متن",
            "سلول‌هایی که فاصله، نویسهٔ نامرئی یا نیم‌فاصلهٔ نادرست دارند؛ "
            "دو مقداری که باید یکی باشند را در گروه‌بندی جدا می‌کنند.",
            padded, "warning"))

    from .profile import TYPE_NUMBER, infer_type
    numeric_as_text: list[str] = []
    date_as_text: list[str] = []
    sample = frame.head(6000)
    for name in frame.columns:
        values = sample[name].dropna()
        if values.empty:
            continue
        kind, _, _ = infer_type(values)
        if kind != TYPE_NUMBER:
            continue
        if frame[name].dtype == object:
            numeric_as_text.append(str(name))
        elif str(frame[name].dtype).startswith("datetime"):
            continue
    for name in frame.columns:
        if frame[name].dtype != object:
            continue
        converted = sample[name].dropna().map(parse_date)
        if len(converted) and converted.notna().mean() >= 0.85:
            date_as_text.append(str(name))

    if numeric_as_text:
        findings.append(Finding(
            OPT_NUMERIC_AS_TEXT, "ستون عددی که متن ذخیره شده",
            "این ستون‌ها عدد هستند ولی به‌صورت متن ذخیره شده‌اند؛ تا تبدیل "
            "نشوند، جمع و میانگین روی آن‌ها غلط است. نام‌ها: " +
            "، ".join(numeric_as_text[:6]) +
            (" و …" if len(numeric_as_text) > 6 else ""),
            len(numeric_as_text), "critical"))

    if date_as_text:
        findings.append(Finding(
            OPT_PARSE_DATES, "ستون تاریخ که متن ذخیره شده",
            "این ستون‌ها تاریخ هستند ولی متن‌اند؛ تا تبدیل نشوند، تحلیل روند "
            "و مقایسهٔ دوره‌ها ممکن نیست. نام‌ها: " +
            "، ".join(date_as_text[:6]) +
            (" و …" if len(date_as_text) > 6 else ""),
            len(date_as_text), "warning"))

    variants = 0
    for name in frame.columns:
        if frame[name].dtype != object:
            continue
        variants += int(frame[name].map(
            lambda value: isinstance(value, str) and clean_text(value) == ""
            and value != "").sum())
    if variants:
        findings.append(Finding(
            OPT_NORMALIZE_NULLS, "سلول خالی که خالی نیست",
            "سلول‌هایی که فقط فاصله یا نویسهٔ نامرئی دارند و به‌ظاهر پر به "
            "نظر می‌رسند ولی مقداری ندارند.",
            variants, "info"))

    if rows and not findings:
        findings.append(Finding(
            "none", "مشکلی پیدا نشد",
            "جدول از نظر خالی‌بودن، تکرار و نوع ستون‌ها سالم است.", 0, "info"))
    return findings


# ------------------------------------------------------------------ اعمال
def _coerce_number(column):
    """یک ستون متن را به عدد تبدیل می‌کند و شمار مقدارهای تبدیل‌شده را می‌دهد."""
    parsed = column.map(parse_number)
    converted = int(parsed.notna().sum())
    original_filled = int(column.map(
        lambda value: clean_text(value) != "").sum())
    if converted == 0:
        return column, 0
    #: اگر بخش بزرگی از مقدارهای پرشده تبدیل نشدند، تبدیل کل ستون را خراب
    #: می‌کند؛ در آن صورت ستون متن می‌ماند و مقدار تبدیل‌شده بی‌اعلام دور
    #: ریخته نمی‌شود.
    if original_filled and converted / original_filled < 0.9:
        return column, 0
    return parsed.astype("float64"), converted


def _coerce_date(column):
    """یک ستون متن را به تاریخ تبدیل می‌کند."""
    parsed = column.map(parse_date)
    filled = int(column.map(lambda value: clean_text(value) != "").sum())
    converted = int(parsed.notna().sum())
    if not converted or (filled and converted / filled < 0.9):
        return column, 0
    return pd.to_datetime(parsed, errors="coerce"), converted


def clean(frame: pd.DataFrame, options: CleanOptions | None = None) -> CleanResult:
    """اعمال اصلاح‌های انتخاب‌شده و برگرداندن جدول تازه با سابقهٔ کامل."""
    chosen = options or CleanOptions()
    findings = detect(frame)
    fixes: list[Fix] = []

    work = frame.copy()
    rows_before, columns_before = work.shape

    #: ۱) ستون‌های کاملاً خالی. تنها حذف ستونی که مجاز است: ستونی که هیچ
    #: مقداری ندارد، اطلاعاتی از دست نمی‌رود.
    if chosen.enabled(OPT_DROP_EMPTY_COLUMNS):
        empty = [name for name in work.columns if work[name].isna().all()]
        if empty:
            work = work.drop(columns=empty)
            fixes.append(Fix(
                OPT_DROP_EMPTY_COLUMNS, "ستون خالی حذف شد",
                "ستون‌های بدون مقدار: " + "، ".join(str(name) for name in empty[:6]) +
                (" و …" if len(empty) > 6 else ""),
                len(empty), destructive=True))

    #: ۲) ردیف‌های کاملاً خالی.
    if chosen.enabled(OPT_DROP_EMPTY_ROWS):
        before = len(work)
        work = work.dropna(axis=0, how="all")
        removed = before - len(work)
        if removed:
            fixes.append(Fix(
                OPT_DROP_EMPTY_ROWS, "ردیف خالی حذف شد",
                "ردیف‌هایی که در هیچ ستونی مقدار نداشتند.",
                removed, destructive=True))

    #: ۳) ردیف‌های تکراری.
    if chosen.enabled(OPT_DROP_DUPLICATES):
        before = len(work)
        work = work.drop_duplicates()
        removed = before - len(work)
        if removed:
            fixes.append(Fix(
                OPT_DROP_DUPLICATES, "ردیف تکراری حذف شد",
                "ردیف‌های یکسان با یک ردیف دیگر. این کار از دو برابر شدن "
                "جمع‌ها جلوگیری می‌کند.",
                removed, destructive=True))

    #: ۴) متن: فاصله و نویسهٔ نامرئی.
    if chosen.enabled(OPT_TRIM_TEXT):
        trimmed = 0
        for name in work.columns:
            if work[name].dtype != object:
                continue
            original = work[name]
            cleaned = original.map(
                lambda value: clean_text(value) if isinstance(value, str) else value)
            #: فقط سلول‌های پرشده مقایسه می‌شوند. استفاده از ``fillna`` برای
            #: مقایسهٔ امن، در pandas هشدار منسوخ‌شدن می‌داد و نوع داده را
            #: بی‌صدا پایین‌می‌آورد.
            mask = original.notna()
            changed = int((original[mask].astype(str)
                           != cleaned[mask].astype(str)).sum())
            if changed:
                work[name] = cleaned
                trimmed += changed
        if trimmed:
            fixes.append(Fix(
                OPT_TRIM_TEXT, "متن یکدست شد",
                "فاصلهٔ اضافی و نویسهٔ نامرئی از ابتدا و انتهای سلول‌ها پاک شد.",
                trimmed))

    #: ۵) تاریخ — پیش از عدد، چون «۲۰۲۴۰۳۰۱» هر دو خوانده می‌شود.
    if chosen.enabled(OPT_PARSE_DATES):
        converted_dates = 0
        names: list[str] = []
        for name in work.columns:
            if work[name].dtype != object:
                continue
            values = work[name].dropna()
            if values.empty:
                continue
            parsed = values.map(parse_date)
            if parsed.notna().mean() < 0.85:
                continue
            work[name], count = _coerce_date(work[name])
            if count:
                converted_dates += count
                names.append(str(name))
        if converted_dates:
            fixes.append(Fix(
                OPT_PARSE_DATES, "ستون تاریخ شناسایی و تبدیل شد",
                "ستون‌های تاریخ‌دار به نوع تاریخ تبدیل شدند تا روند و مقایسهٔ "
                "دوره‌ها ممکن شود. نام‌ها: " + "، ".join(names[:6]) +
                (" و …" if len(names) > 6 else ""),
                converted_dates))

    #: ۶) عددی که متن ذخیره شده.
    if chosen.enabled(OPT_NUMERIC_AS_TEXT):
        converted_numbers = 0
        names = []
        for name in work.columns:
            if work[name].dtype != object:
                continue
            values = work[name].dropna()
            if values.empty:
                continue
            if values.map(parse_number).notna().mean() < 0.85:
                continue
            work[name], count = _coerce_number(work[name])
            if count:
                converted_numbers += count
                names.append(str(name))
        if converted_numbers:
            fixes.append(Fix(
                OPT_NUMERIC_AS_TEXT, "متن عددی به عدد تبدیل شد",
                "سلول‌هایی مثل «۱٬۲۰۰٬۰۰۰» یا «۲۵۰٬۰۰۰ ریال» به عدد تبدیل "
                "شدند. نام ستون‌ها: " + "، ".join(names[:6]) +
                (" و …" if len(names) > 6 else ""),
                converted_numbers))

    #: ۷) خالی‌های پنهان.
    if chosen.enabled(OPT_NORMALIZE_NULLS):
        normalized = 0
        for name in work.columns:
            if work[name].dtype != object:
                continue
            series = work[name]
            #: شرط عمداً «رشتهٔ خالی» است و نه «رشتهٔ خالی *غیر از* ""».
            #: گام یکدست‌سازی متن پیش از این اجرا می‌شود و « » را به ""
            #: تبدیل می‌کند؛ اگر شرط سخت‌گیرانه بود، مقدار یکدست‌شده هرگز
            #: خالی ثبت نمی‌شد و کاربر فکر می‌کرد سلول‌ها پر هستند.
            mask = series.map(lambda value: isinstance(value, str)
                              and clean_text(value) == "")
            normalized += int(mask.sum())
            if mask.any():
                work.loc[mask, name] = pd.NA
        if normalized:
            fixes.append(Fix(
                OPT_NORMALIZE_NULLS, "سلول خالی، خالی ثبت شد",
                "سلول‌هایی که فقط فاصله داشتند به مقدار خالی تبدیل شدند تا در "
                "شمارش خالی‌ها درست دیده شوند.",
                normalized))

    work = work.reset_index(drop=True)
    return CleanResult(
        frame=work, findings=findings, fixes=fixes,
        rows_before=int(rows_before), rows_after=int(len(work)),
        columns_before=int(columns_before), columns_after=int(work.shape[1]),
    )


def options_meta() -> list[dict]:
    """شرح گزینه‌ها برای نمایش در فرم — یک منبع حقیقت."""
    return [
        {"key": OPT_DROP_EMPTY_ROWS, "title": "حذف ردیف‌های کاملاً خالی",
         "detail": "ردیفی که هیچ مقداری ندارد.", "affects": "تعداد ردیف"},
        {"key": OPT_DROP_DUPLICATES, "title": "حذف ردیف‌های تکراری",
         "detail": "جلوگیری از دو برابر شدن جمع‌ها و میانگین‌ها.", "affects": "تعداد ردیف"},
        {"key": OPT_DROP_EMPTY_COLUMNS, "title": "حذف ستون‌های کاملاً خالی",
         "detail": "تنها ستونی که حذفش اطلاعاتی از دست نمی‌دهد.", "affects": "تعداد ستون"},
        {"key": OPT_TRIM_TEXT, "title": "یکدست‌سازی متن",
         "detail": "فاصلهٔ اضافی، نویسهٔ نامرئی و نیم‌فاصلهٔ نادرست.", "affects": "مقدار سلول"},
        {"key": OPT_NUMERIC_AS_TEXT, "title": "تبدیل متن عددی به عدد",
         "detail": "«۱٬۲۰۰٬۰۰۰ ریال» به عدد ۱۲۰۰۰۰۰ تبدیل می‌شود.", "affects": "نوع ستون"},
        {"key": OPT_PARSE_DATES, "title": "تبدیل متن تاریخ به تاریخ",
         "detail": "تاریخ شمسی و میلادی، با ارقام فارسی.", "affects": "نوع ستون"},
        {"key": OPT_NORMALIZE_NULLS, "title": "ثبت سلول خالی به‌عنوان خالی",
         "detail": "سلولی که فقط فاصله دارد، خالی شمرده می‌شود.", "affects": "شمارش خالی"},
    ]
