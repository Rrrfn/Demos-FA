# -*- coding: utf-8 -*-
"""خواندن جدول از XLSX و CSV با تشخیص سرصفحه و مدیریت فایل‌های واقعی.

سه مسئله‌ای که فایل‌های واقعی می‌سازند و اینجا حل می‌شوند:

۱) **سرصفحه جابه‌جا است.** خیلی از فایل‌ها چند سطر عنوان و توضیح بالای جدول
   دارند. اگر سطر اول سرصفحه فرض شود، نام ستون‌ها «کارگزاری» و «گزارش فروش
   دوره اول» می‌شود و داده زیرشان گم می‌شود. اینجا چند سطر اول امتحان و
   بهترین سرصفحه انتخاب می‌شود.

۲) **CSV با کدگذاری نامعلوم.** فایل فارسی ویندوزی ``cp1256`` است، خروجی اکسل
   ``utf-8-sig``، و بقیه ``utf-8``. هر سه امتحان می‌شوند و *کدگذاری واقعی* در
   فراداده ثبت می‌شود تا در گزارش گفته شود.

۳) **CSV با جداکننده نامعلوم.** ویرگول، نقطه‌ویرگول، تب و لوله. تشخیص خودکار
   pandas روی فایل‌های تک‌ستونی اشتباه می‌کند؛ اینجا با شمردن نویسه در چند سطر
   اول و ترجیح جداکننده‌ای که جدول *واقعی* می‌سازد انتخاب می‌شود.

سقف سطر: فایل بزرگ در حافظه باز می‌شود ولی بیش از سقف خوانده نمی‌شود، و این
بریدن **به کاربر اعلام می‌شود** — بریدن بی‌اعلام، گزارش را بی‌صدا غلط می‌کند.
"""
from __future__ import annotations

import csv
import os
import zipfile
from dataclasses import dataclass, field

import pandas as pd

from ..config import (CSV_ENCODINGS, CSV_SEPARATORS, MAX_COLUMNS, MAX_ROWS,
                      TYPE_SAMPLE_ROWS)
from ..errors import (CorruptFileError, EmptyDatasetError, EmptyFileError,
                      NoHeaderError, TooManyColumnsError)

#: شمار سطرهایی که برای پیدا کردن سرصفحه امتحان می‌شود.
HEADER_SEARCH_ROWS = 12


@dataclass
class ReadResult:
    """نتیجهٔ خواندن یک فایل — جدول به‌همراه آنچه *دربارهٔ* خواندن باید گفته شود."""

    frame: pd.DataFrame
    #: نام شیتی که خوانده شد (فقط XLSX).
    sheet: str = ""
    #: کدگذاری مؤثر (فقط CSV).
    encoding: str = ""
    #: جداکنندهٔ مؤثر (فقط CSV).
    separator: str = ""
    #: شمارهٔ سطری که سرصفحه بوده (از یک).
    header_row: int = 1
    #: سطرهایی که به‌عنوان عنوان پیش از سرصفحه رد شدند.
    skipped_rows: int = 0
    #: آیا فایل به سقف سطر رسید؟
    truncated: bool = False
    #: شمار سطرهای موجود در فایل (اگر معلوم باشد) — برای گفتن «چند سطر ماند».
    total_rows: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return int(len(self.frame))

    @property
    def columns(self) -> int:
        return int(self.frame.shape[1])

    def summary(self) -> dict:
        return {
            "rows": self.rows,
            "columns": self.columns,
            "sheet": self.sheet,
            "encoding": self.encoding,
            "separator": self.separator,
            "header_row": self.header_row,
            "skipped_rows": self.skipped_rows,
            "truncated": self.truncated,
            "total_rows": self.total_rows,
            "warnings": list(self.warnings),
        }


# ------------------------------------------------------------------ کمکی‌ها
def _looks_like_header(frame: pd.DataFrame) -> bool:
    """آیا ردیف اول این جدول *نام ستون* است یا داده؟

    ملاک «متن بودن» کافی نیست، چون CSV با ``dtype=object`` خوانده می‌شود و
    در نتیجه اعداد هم رشته می‌مانند. پس معیار سخت‌گیرانه‌تر است: دست‌کم نیمی
    از مقدارهای ردیف اول باید عدد و تاریخ *نباشند* تا آن ردیف نام ستون
    شمرده شود.

    بدون این تفاوت، جدولی که سرصفحه ندارد بی‌هشدار خوانده می‌شد و ردیف اول
    دادهٔ واقعی به‌عنوان نام ستون از تحلیل بیرون می‌رفت.
    """
    from .cells import parse_date, parse_number

    if frame.empty or len(frame.columns) == 0:
        return False
    first = frame.iloc[0]
    filled = int(first.notna().sum())
    if filled < max(1, int(len(first) * 0.6)):
        return False
    textual = 0
    for value in first:
        if pd.isna(value):
            continue
        if isinstance(value, str) and parse_number(value) is None \
                and parse_date(value) is None:
            textual += 1
    return textual >= max(1, int(len(first) * 0.5))


def _dedupe_columns(names: list) -> list[str]:
    """نام ستون‌های یکتا و غیرخالی.

    اکسل اجازه می‌دهد چند ستون هم‌نام باشند و ستون بی‌نام داشته باشد؛ هر دو
    برای pandas مسئله می‌سازند (``df[col]`` یک DataFrame برمی‌گرداند نه Series).
    """
    result: list[str] = []
    seen: dict[str, int] = {}
    for index, name in enumerate(names, start=1):
        label = str(name).strip()
        if not label or label.lower().startswith("unnamed:"):
            label = ""
        if not label:
            label = f"ستون {index}"
        if label in seen:
            seen[label] += 1
            label = f"{label} ({seen[label]})"
        else:
            seen[label] = 1
        result.append(label)
    return result


def _prepare(frame: pd.DataFrame, header_row: int, skipped: int) -> pd.DataFrame:
    """نام ستون‌ها را پاک می‌کند و ردیف‌های کاملاً خالی را می‌ریزد."""
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    frame.columns = _dedupe_columns(list(frame.columns))
    frame = frame.reset_index(drop=True)
    return frame


def _guard(frame: pd.DataFrame, truncated: bool, total: int | None,
           warnings: list[str]) -> None:
    """بررسی‌های پس از خواندن: خالی نبودن، پهنای معقول، سقف سطر."""
    if frame.empty or frame.shape[1] == 0:
        raise EmptyDatasetError(
            "فایل خوانده شد ولی هیچ سطر داده‌ای نداشت. لطفاً فایلی با حداقل "
            "یک سطر داده و یک سرصفحه بفرستید.")
    if frame.shape[1] > MAX_COLUMNS:
        raise TooManyColumnsError(
            f"فایل {frame.shape[1]} ستون دارد و سقف مجاز {MAX_COLUMNS} ستون "
            "است. ستون‌های غیرضروری را حذف کنید.")
    if truncated:
        warnings.append(
            f"فایل بیش از {MAX_ROWS:,} سطر داشت؛ فقط {MAX_ROWS:,} سطر اول "
            "خوانده شد. تحلیل روی همین بخش انجام شده است.".replace(",", "٬"))


# ------------------------------------------------------------------ CSV
def _sniff_separator(sample: str) -> str:
    """انتخاب جداکننده با شمردن نویسه در چند سطر اول.

    ترجیح به جداکننده‌ای است که بیشترین *یکنواختی* را بدهد: اگر هر سطر همان
    تعداد جداکننده داشته باشد، آن جداکننده ساختار واقعی فایل است. تشخیص
    خودکار csv روی فایل تک‌ستونی نقطه‌ویرگول را ویرگول می‌بیند.
    """
    lines = [line for line in sample.splitlines() if line.strip()][:20]
    if not lines:
        return ","
    best, best_score = ",", -1.0
    for candidate in (",", ";", "\t", "|"):
        counts = [line.count(candidate) for line in lines]
        if max(counts) == 0:
            continue
        mode_count = max(set(counts), key=counts.count)
        if mode_count == 0:
            continue
        #: امتیاز = نسبت سطرهایی که همان تعداد جداکننده را دارند، وزن‌دار با
        #: شمار ستون‌های حاصل. جدول پهن‌تر با ساختار یکنواخت برنده است.
        consistent = counts.count(mode_count) / len(counts)
        score = consistent * (mode_count + 1)
        if score > best_score:
            best, best_score = candidate, score
    return best


#: نشانه‌های ابتدای فایل برای کدگذاری‌های دو بایتی و چهار بایتی.
WIDE_BOMS = ((b"\xff\xfe\x00\x00", "UTF-32"), (b"\x00\x00\xfe\xff", "UTF-32"),
             (b"\xff\xfe", "UTF-16"), (b"\xfe\xff", "UTF-16"))


def _detect_wide_encoding(path: str) -> str:
    """کدگذاری UTF-16 / UTF-32 را از نشانهٔ ابتدای فایل تشخیص می‌دهد."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(4)
    except OSError:
        return ""
    for signature, label in WIDE_BOMS:
        if head.startswith(signature):
            return label
    #: فایل UTF-16 بدون BOM: نویسه‌های لاتین با بایت صفر بینشان می‌آیند.
    if len(head) >= 4 and head[0::2].count(b"\x00") >= 2 and head[1] == 0:
        return "UTF-16"
    return ""


def _read_with_encoding(path: str, encoding: str, *, skip_bad: bool):
    """خواندن CSV با یک کدگذاری مشخص؛ جداکننده هر بار تازه تشخیص داده می‌شود."""
    with open(path, "r", encoding=encoding, newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        separator = _sniff_separator(sample)
        frame = pd.read_csv(
            handle, sep=separator, engine="python", dtype=object,
            skip_blank_lines=True, nrows=MAX_ROWS + 1,
            keep_default_na=True, na_values=["", " ", "-", "--", "—"],
            on_bad_lines="skip" if skip_bad else "error",
        )
    return separator, frame


def _read_csv(path: str, warnings: list[str]) -> ReadResult:
    #: فایل‌های UTF-16 / UTF-32 با فهرست کدگذاری‌های ما اشتباه خوانده می‌شوند:
    #: بایت‌هایشان با cp1256 "موفق" رمزگشایی می‌شود و نتیجه‌اش متنی بی‌معنا
    #: است که بی‌صدا وارد تحلیل می‌شود. پس با نشانهٔ ابتدای فایل تشخیص داده
    #: و با پیام روشن رد می‌شوند.
    wide = _detect_wide_encoding(path)
    if wide:
        raise CorruptFileError(
            f"کدگذاری فایل {wide} است و پشتیبانی نمی‌شود. فایل را در اکسل با "
            "قالب «CSV UTF-8» ذخیره کنید.", detail=wide)

    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            separator, frame = _read_with_encoding(path, encoding, skip_bad=False)
        except UnicodeDecodeError as error:
            last_error = error
            continue
        except pd.errors.ParserError as error:
            #: ساختار ناهموار (سطرهایی با تعداد ستون متفاوت) دلیل رایج خطای
            #: تجزیه است و فایل را غیرقابل‌استفاده نمی‌کند. یک بار دیگر با
            #: رد کردن سطرهای خراب می‌خوانیم و *تعدادشان را اعلام می‌کنیم* —
            #: رد کردن بی‌اعلام، تحلیل را بی‌صدا ناقص می‌کند.
            try:
                separator, frame = _read_with_encoding(path, encoding,
                                                       skip_bad=True)
            except (UnicodeDecodeError, pd.errors.ParserError,
                    pd.errors.EmptyDataError, csv.Error, OSError) as nested:
                raise CorruptFileError(
                    "ساختار فایل CSV قابل خواندن نیست. فایل ممکن است خراب یا "
                    "نیمه‌بریده باشد.", detail=f"{error} | {nested}") from error
            warnings.append(
                "برخی سطرها با ساختار جدول نمی‌خواندند (تعداد ستون متفاوت) و "
                "رد شدند؛ عددهای این گزارش روی سطرهای سالم است.")
        except (csv.Error, pd.errors.EmptyDataError, OSError) as error:
            #: ``EmptyDataError`` وقتی بالا می‌آید که فایل هیچ ستون قابل تجزیه‌ای
            #: ندارد — مثلاً بایت‌های دودویی با پسوند csv. بدون گرفتنش، خطای
            #: خام pandas به کاربر می‌رسید.
            raise CorruptFileError(
                "ساختار فایل CSV قابل خواندن نیست. فایل ممکن است خراب یا "
                "نیمه‌بریده باشد.", detail=str(error)) from error

        if frame.shape[1] == 1:
            #: جداکنندهٔ دیگر را امتحان می‌کنیم: یک ستون تک، معمولاً یعنی
            #: جداکننده اشتباه حدس زده شده.
            for alternative in CSV_SEPARATORS:
                if alternative in (None, separator):
                    continue
                try:
                    with open(path, "r", encoding=encoding, newline="") as handle:
                        retry = pd.read_csv(handle, sep=alternative, engine="python",
                                            dtype=object, nrows=MAX_ROWS + 1,
                                            keep_default_na=True,
                                            na_values=["", " ", "-", "--", "—"])
                except (UnicodeDecodeError, csv.Error, pd.errors.ParserError, OSError):
                    continue
                if retry.shape[1] > frame.shape[1]:
                    frame, separator = retry, alternative

        truncated = len(frame) > MAX_ROWS
        if truncated:
            frame = frame.iloc[:MAX_ROWS]
        warnings.append(f"کدگذاری تشخیص‌داده‌شده: {encoding}")
        result = ReadResult(
            frame=frame, encoding=encoding,
            separator="\\t" if separator == "\t" else separator,
            truncated=truncated, warnings=warnings,
            total_rows=None,
        )
        return result

    raise CorruptFileError(
        "کدگذاری فایل شناسایی نشد. فایل را با کدگذاری UTF-8 به‌صورت CSV "
        "ذخیره کنید.", detail=str(last_error))


# ------------------------------------------------------------------ XLSX
def _read_xlsx(path: str, warnings: list[str]) -> ReadResult:
    try:
        book = pd.ExcelFile(path, engine="openpyxl")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise CorruptFileError(
            "فایل XLSX باز نشد یا ساختارش آسیب دیده است. اگر فایل در اکسل "
            "باز می‌شود، آن را دوباره با فرمت «Excel Workbook (.xlsx)» ذخیره "
            "کنید.", detail=str(error)) from error

    if not book.sheet_names:
        raise EmptyFileError("کارپوشه هیچ شیتی ندارد.")

    skipped: list[str] = []
    for name in book.sheet_names:
        try:
            raw = book.parse(name, header=None, dtype=object,
                             nrows=MAX_ROWS + HEADER_SEARCH_ROWS + 2)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            skipped.append(f"{name}: {error}")
            continue
        if raw.empty or raw.dropna(how="all").empty:
            skipped.append(name)
            continue

        header_index = _find_header(raw)
        header = [str(value).strip() if not pd.isna(value) else f"ستون {i + 1}"
                  for i, value in enumerate(raw.iloc[header_index])]
        frame = raw.iloc[header_index + 1:].copy()
        frame.columns = header
        frame = frame.iloc[:MAX_ROWS] if len(frame) > MAX_ROWS else frame
        truncated = len(raw) > MAX_ROWS + header_index + 1

        warnings.append(f"شیت خوانده‌شده: {name}")
        if header_index:
            warnings.append(
                f"{header_index} سطر ابتدایی به‌عنوان عنوان شناسایی و رد شد.")
        if len({name for name in book.sheet_names}) > 1:
            warnings.append(
                f"کارپوشه {len(book.sheet_names)} شیت دارد؛ فقط شیت "
                f"«{name}» پردازش شد.")
        result = ReadResult(
            frame=frame, sheet=name, header_row=header_index + 1,
            skipped_rows=header_index, truncated=truncated,
            warnings=warnings, total_rows=None,
        )
        return result

    raise EmptyDatasetError(
        "هیچ شیتی در کارپوشه داده‌ای نداشت. لطفاً شیتی با سرصفحه و سطر داده "
        "بفرستید." + (f" (شیت‌های ردشده: {'، '.join(skipped)})" if skipped else ""))


def _find_header(raw: pd.DataFrame) -> int:
    """پیدا کردن بهترین سطر سرصفحه در چند سطر اول.

    معیار: سطری که پرترین و متنی‌ترین باشد. سطرهای عنوان معمولاً یک سلول
    دارند و بقیه خالی است، پس با این معیار رد می‌شوند.
    """
    limit = min(HEADER_SEARCH_ROWS, len(raw))
    best_index, best_score = 0, -1.0
    for index in range(limit):
        row = raw.iloc[index]
        filled = int(row.notna().sum())
        if filled == 0:
            continue
        width = max(1, raw.shape[1])
        text_like = sum(1 for value in row if isinstance(value, str) and value.strip())
        #: سطر سرصفحه هم پر است و هم بیشترش متن است؛ سطر عنوان پر نیست.
        score = (filled / width) * 2 + (text_like / width)
        if index == 0:
            score += 0.35                       #: سرصفحه در سطر اول حالت رایج است
        if score > best_score:
            best_index, best_score = index, score
    return best_index


# ------------------------------------------------------------------ دروازه
def read_table(path: str, extension: str, warnings: list[str] | None = None) -> ReadResult:
    """خواندن جدول از مسیر فایل بر اساس پسوند.

    بریدن سطر و کدگذاری در همان ``ReadResult`` برگردانده می‌شود تا لایهٔ
    بالاتر بتواند آن را به کاربر بگوید، نه این‌که بی‌صدا واقعیت را عوض کند.
    """
    collected = list(warnings or [])
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise EmptyFileError("فایل خالی است و داده‌ای برای تحلیل ندارد.")

    if extension == "csv":
        result = _read_csv(path, collected)
    elif extension == "xlsx":
        result = _read_xlsx(path, collected)
    else:
        raise CorruptFileError(
            f"خواندن قالب «{extension}» پشتیبانی نمی‌شود.")

    if not _looks_like_header(result.frame):
        #: سرصفحه نبود: نام ستون‌ها ساختگی است و ردیف اول داده هم از دست
        #: نمی‌رود، چون ``_find_header`` در بدترین حالت سطر اول را می‌گیرد.
        result.warnings.append(
            "سطر اول ساختاری شبیه نام ستون نداشت؛ نام ستون‌ها خودکار ساخته "
            "شد. اگر جدول شما سرصفحه دارد، آن را در سطر اول فایل بگذارید.")

    result.frame = _prepare(result.frame, result.header_row, result.skipped_rows)
    _guard(result.frame, result.truncated, result.total_rows, result.warnings)
    return result
