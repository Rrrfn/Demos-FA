# -*- coding: utf-8 -*-
"""تحلیل گروهی — بارگذاری CSV، اعتبارسنجی، پیش‌بینی و خلاصه.

سه تصمیم که این ماژول را از «یک حلقه روی ردیف‌ها» جدا می‌کند:

۱) **اعتبارسنجی پیش از محاسبه.** فایل بزرگ، فایل بدون ستون متن، فایل خالی و
   فایل با کدگذاری اشتباه، هر کدام پیام خودشان را می‌گیرند؛ هیچ‌کدام به خطای
   ۵۰۰ تبدیل نمی‌شوند و هیچ‌کدام بی‌صدا رد نمی‌شوند.

۲) **ردیف‌های مشکل‌دار حذف نمی‌شوند، علامت می‌خورند.** ردیفی که متنش خالی است
   یا واژه‌هایش برای مدل ناشناس‌اند برچسب نمی‌گیرد و در ستون وضعیت مشخص
   می‌شود. حذف بی‌صدا یعنی کاربر فکر می‌کند فایلش کامل پردازش شده است.

۳) **پیش‌بینی دسته‌ای است.** یک فراخوانی مدل برای همهٔ ردیف‌ها، نه یکی برای
   هرکدام؛ تفاوتش در نتیجه صفر و در زمان چند برابر است.
"""
from __future__ import annotations

import io

import pandas as pd

from .config import (DATE_COLUMN_NAMES, LABELS, MAX_ANALYZE_CHARS,
                     MAX_BATCH_ROWS, MAX_UPLOAD_BYTES, TEXT_COLUMN_NAMES)
from .explain import top_signals_many
from .labels import fa_number, fa_percent, sentiment_label, to_persian_digits
from .model import predict_many, vocabulary
from .normalize import tokenize

#: وضعیت هر ردیف. این کدها در رابط به فارسی نگاشته می‌شوند و به کاربر
#: می‌گویند *چرا* آن ردیف برچسب قطعی نگرفته است.
STATE_TEXT = {
    "ok": "تحلیل شد",
    "empty": "متن خالی",
    "no_signal": "بدون توکن معنادار",
    "out_of_domain": "خارج از واژگان مدل",
    "thin_coverage": "پوشش واژگان کم",
}

#: ستون‌های فایل خروجی — یک منبع حقیقت برای نمایش و دانلود.
OUTPUT_COLUMNS = ("ردیف", "متن", "برچسب", "اطمینان", "وضعیت", "واژه‌های مؤثر")


class BatchError(ValueError):
    """خطای قابل‌نمایش به کاربر — نه خطای برنامه."""


def read_table(payload: bytes) -> tuple[pd.DataFrame, list[str]]:
    """بایت فایل → جدول، همراه با هشدارها.

    کدگذاری: ``utf-8-sig`` (خروجی اکسل)، سپس ``utf-8`` و در نهایت ``cp1256``
    که کدگذاری رایج فایل‌های فارسی ویندوزی است. بدون این ترتیب، فایل اکسل
    فارسی بی‌صدا به متن آشغال تبدیل می‌شود.
    """
    if not payload:
        raise BatchError("فایل خالی است.")
    if len(payload) > MAX_UPLOAD_BYTES:
        limit = fa_number(MAX_UPLOAD_BYTES / (1024 * 1024))
        raise BatchError(f"حجم فایل بیش از حد مجاز است ({limit} مگابایت).")

    frame = None
    for encoding in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            frame = pd.read_csv(io.BytesIO(payload), encoding=encoding,
                                dtype=str, keep_default_na=False)
            break
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            raise BatchError("فایل هیچ سطر داده‌ای ندارد.")
        except pd.errors.ParserError:
            raise BatchError("فایل CSV خوانده نشد؛ جداکننده یا ساختار سطرها را بررسی کنید.")
    if frame is None:
        raise BatchError("کدگذاری فایل پشتیبانی نمی‌شود؛ آن را با UTF-8 ذخیره کنید.")

    warnings: list[str] = []
    if len(frame) > MAX_BATCH_ROWS:
        warnings.append(
            f"فایل {fa_number(len(frame))} سطر داشت؛ "
            f"تنها {fa_number(MAX_BATCH_ROWS)} سطر نخست تحلیل شد.")
        frame = frame.head(MAX_BATCH_ROWS)
    if frame.empty:
        raise BatchError("فایل هیچ سطر داده‌ای ندارد.")
    return frame.reset_index(drop=True), warnings


def detect_columns(frame: pd.DataFrame) -> tuple[str, str | None, bool]:
    """ستون متن و ستون تاریخ؛ ``bool`` یعنی نام ستون حدس زده شده است.

    اگر هیچ ستون متنی با نام رایج پیدا نشود، ستون نخست به‌عنوان متن در نظر
    گرفته می‌شود و *همین* به کاربر گفته می‌شود. حدس بی‌اعلام بدترین کار است.
    """
    lowered = {str(column).strip().lower(): str(column) for column in frame.columns}
    text_column = next((lowered[name.lower()] for name in TEXT_COLUMN_NAMES
                        if name.lower() in lowered), None)
    date_column = next((lowered[name.lower()] for name in DATE_COLUMN_NAMES
                        if name.lower() in lowered), None)
    guessed = text_column is None
    return (text_column or str(frame.columns[0])), date_column, guessed


def analyse_rows(pipe, texts: list[str]) -> list[dict]:
    """تحلیل هر ردیف — برچسب، اطمینان، وضعیت و واژه‌های مؤثر.

    ردیف‌هایی که سیگنال کافی ندارند از فرآیند پیش‌بینی کنار گذاشته می‌شوند و
    بعد در جای خودشان وضعیت «تحلیل‌نشده» می‌گیرند. صدا زدن مدل روی متن خالی
    برچسبی با اطمینان عددی می‌دهد که معنایش صفر است ولی ظاهرش معتبر.
    """
    cleaned = [(text or "")[:MAX_ANALYZE_CHARS] for text in texts]
    vocabulary_terms = vocabulary(pipe)
    analysable = [index for index, text in enumerate(cleaned) if text.strip()]
    subset = [cleaned[index] for index in analysable]

    predictions = predict_many(pipe, subset) if subset else []
    winners = [row["label"] for row in predictions]
    signals = top_signals_many(pipe, subset, winners) if subset else []

    results: list[dict] = []
    for position, index in enumerate(analysable):
        text = cleaned[index]
        tokens = tokenize(text)
        known = [token for token in tokens
                 if token.lstrip("نـ") in vocabulary_terms]
        coverage = (len(known) / len(tokens)) if tokens else 0.0
        if not tokens:
            state = "no_signal"
        elif not known:
            state = "out_of_domain"
        elif coverage < 0.5:
            state = "thin_coverage"
        else:
            state = "ok"
        row = predictions[position]
        graded = state == "ok"
        results.append({
            "index": index,
            "text": text,
            "label": row["label"] if graded else "",
            "label_fa": sentiment_label(row["label"]) if graded else "—",
            "confidence": row["confidence"] if graded else None,
            "proba": row["proba"] if graded else {},
            "state": state,
            "state_fa": STATE_TEXT[state],
            "tokens": len(tokens),
            "known": len(known),
            "coverage": round(coverage, 4),
            "signals": (signals[position] if position < len(signals) else []),
        })

    for index in range(len(cleaned)):
        if index in analysable:
            continue
        results.append({
            "index": index, "text": cleaned[index], "label": "", "label_fa": "—",
            "confidence": None, "proba": {}, "state": "empty",
            "state_fa": STATE_TEXT["empty"], "tokens": 0, "known": 0,
            "coverage": 0.0, "signals": [],
        })
    results.sort(key=lambda item: item["index"])
    return results


def summarise(results: list[dict]) -> dict:
    """خلاصهٔ تحلیل گروهی — ترکیب برچسب‌ها، اطمینان و دلایل تحلیل‌نشدن.

    مخرجِ درصدها فقط ردیف‌های *تحلیل‌شده* است. با آوردن ردیف‌های تحلیل‌نشده در
    مخرج، درصدها بی‌معنا می‌شوند و کاربر فکر می‌کند فایلش کامل پردازش شده است.
    """
    analysed = [row for row in results if row["state"] == "ok"]
    counts = {code: sum(1 for row in analysed if row["label"] == code)
              for code in LABELS}
    total = sum(counts.values())
    confidences = [row["confidence"] for row in analysed
                   if row["confidence"] is not None]
    skipped: dict[str, int] = {}
    for row in results:
        if row["state"] != "ok":
            skipped[row["state_fa"]] = skipped.get(row["state_fa"], 0) + 1
    return {
        "rows": len(results),
        "analysed": total,
        "skipped": len(results) - total,
        "skipped_reasons": skipped,
        "counts": counts,
        "shares": {code: (counts[code] / total if total else 0.0) for code in LABELS},
        "mean_confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
        "label_fa": {code: sentiment_label(code) for code in LABELS},
    }


def to_frame(results: list[dict]) -> pd.DataFrame:
    """خروجی جدولی با ستون‌های فارسی.

    متن کامل در خروجی می‌ماند: کاربر باید بتواند هر ردیف را به کامنت اصلی‌اش
    نسبت بدهد، وگرنه فایل خروجی بی‌فایده است.
    """
    rows = []
    for row in results:
        confidence = row["confidence"]
        rows.append({
            "ردیف": to_persian_digits(row["index"] + 1),
            "متن": row["text"],
            "برچسب": row["label_fa"],
            #: رقم فارسی در خروجی هم رعایت می‌شود: این فایل متنِ محصول است،
            #: نه یک واسط ماشینی. ماشین‌ها از ``/api`` عدد خام می‌گیرند.
            "اطمینان": ("" if confidence is None
                        else fa_percent(confidence, decimals=1)),
            "وضعیت": row["state_fa"],
            "واژه‌های مؤثر": "، ".join(row["signals"]),
        })
    return pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))


def to_csv_bytes(results: list[dict], name: str = "") -> tuple[bytes, str]:
    """خروجی CSV با BOM تا اکسل ویندوزی متن فارسی را درست بخواند.

    بی‌BOM، اکسل فایل را cp1256 می‌خواند و متن فارسی به آشغال بدل می‌شود؛
    کاربری که فایل را باز می‌کند فکر می‌کند برنامه خراب است.
    """
    frame = to_frame(results)
    payload = frame.to_csv(index=False).encode("utf-8-sig")
    stem = (name or "hassanj").rsplit(".", 1)[0] or "hassanj"
    return payload, f"{stem}-تحلیل.csv"


def preview(results: list[dict], limit: int = 50) -> list[dict]:
    """چند ردیف نخست برای نمایش در جدول صفحه.

    محدود است چون جدول هزارردیفی هم مرورگر را سنگین می‌کند و هم انسانی نیست؛
    کاربر برای فایل کامل، خروجی CSV را دانلود می‌کند.
    """
    return results[:limit]


def persian_row(row: dict) -> dict:
    """آماده‌سازی یک ردیف برای نمایش — رقم فارسی و برچسب فارسی."""
    confidence = row.get("confidence")
    return {
        "index": to_persian_digits(row["index"] + 1),
        "text": row["text"],
        "label": row["label_fa"],
        "confidence": ("—" if confidence is None
                       else f"{to_persian_digits(f'{confidence * 100:.0f}')}٪"),
        "state": row["state_fa"],
        "signals": row["signals"],
        "coverage": to_persian_digits(f"{row['coverage'] * 100:.0f}"),
    }
