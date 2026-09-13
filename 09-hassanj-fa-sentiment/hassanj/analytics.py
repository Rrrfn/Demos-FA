# -*- coding: utf-8 -*-
"""تحلیل‌های تحلیلی — هر عددی که در صفحهٔ «تحلیل» و «مدل» دیده می‌شود.

دو قاعده در کل این ماژول رعایت می‌شود:

۱) **هرچه نمایش داده می‌شود محاسبه است، نه ادعا.** ترکیب کلاس‌ها، توزیع
   اطمینان، اطمینان به‌تفکیک پوشش واژگان، و فهرست خطاها همه روی دادهٔ واقعی
   همین مخزن حساب می‌شوند.

۲) **پیش‌بینی مدل جدا از برچسب واقعی نشان داده می‌شود.** ترکیب واقعی دیتاست و
   ترکیب پیش‌بینی‌شده دو چیز مختلف‌اند؛ قاطی‌کردنشان همان کاری است که یک دموی
   سطحی می‌کند. هر جا هر دو معنا دارند، هر دو می‌آیند.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from .config import LABELS, N_PER_CLASS
from .dataset import JALALI_WINDOW, class_counts_per_month
from .labels import sentiment_label
from .model import predict_many, top_terms, vocabulary
from .normalize import tokenize


def _label_counts(codes: list[str]) -> dict[str, int]:
    counter = Counter(codes)
    return {code: int(counter.get(code, 0)) for code in LABELS}


def _shares(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values()) or 1
    return {code: round(value / total, 4) for code, value in counts.items()}


def actual_mix(frame: pd.DataFrame) -> dict:
    """ترکیب برچسب‌های واقعی دیتاست نمونه.

    این عدد از خود دیتاست می‌آید و به مدل کاری ندارد؛ فقط نشان می‌دهد دیتاست
    چطور ساخته شده است.
    """
    counts = _label_counts([str(code) for code in frame["label"]])
    return {"counts": counts, "shares": _shares(counts),
            "total": int(sum(counts.values()))}


def predicted_mix(pipe, texts: list[str]) -> dict:
    """ترکیب پیش‌بینی‌شدهٔ مدل روی همان متن‌ها.

    کنار ترکیب واقعی می‌آید تا اگر مدل یک کلاس را بیش از واقع پیش‌بینی
    می‌کند، دیده شود.
    """
    rows = predict_many(pipe, texts)
    counts = _label_counts([row["label"] for row in rows])
    confidences = [row["confidence"] for row in rows]
    return {
        "counts": counts,
        "shares": _shares(counts),
        "total": len(rows),
        "mean_confidence": round(float(np.mean(confidences)), 4) if rows else 0.0,
        "band_counts": _band_counts(confidences),
    }


def _band_counts(confidences: list[float]) -> dict[str, int]:
    from .labels import confidence_band

    counter = Counter(confidence_band(value) for value in confidences)
    return {band: int(counter.get(band, 0)) for band in ("high", "medium", "low")}


def comparison(pipe, frame: pd.DataFrame) -> list[dict]:
    """واقعی در برابر پیش‌بینی‌شده — به تفکیک هر کلاس.

    برای نمودار میله‌های گروهی. اختلاف هر جفت، همان چیزی است که مدل روی
    دیتاست نمونه اشتباه می‌بیند.
    """
    texts = [str(text) for text in frame["text"]]
    actual = actual_mix(frame)
    predicted = predicted_mix(pipe, texts)
    return [{
        "code": code,
        "label": sentiment_label(code),
        "actual": actual["shares"][code],
        "predicted": predicted["shares"][code],
    } for code in LABELS]


def monthly_mix(frame: pd.DataFrame) -> list[dict]:
    """ترکیب کلاس‌ها ماه‌به‌ماه — روند *خودِ دیتاست*.

    این روند از جدول ``MIX_BY_MONTH`` در ``config`` می‌آید و در صفحهٔ متدولوژی
    همین‌طور گفته شده: صفتی از دیتاست نمونه است، نه ادعایی دربارهٔ بازار.

    **دسته‌بندی روی پنجره‌های اعلام‌شده انجام می‌شود، نه روی ماه میلادی.** یک
    بار روی ماه میلادی گروه‌بندی شد و دو اشکال واقعی بیرون آمد: مرزهای ماه
    میلادی با مرزهای پنجرهٔ دیتاست یکی نیستند، پس هفت سطل می‌ساخت در حالی که
    جدول اعلام‌شده شش ماه دارد؛ و برچسب سطل هفتم رقم لاتین به رابط می‌ریخت.
    الان هر ردیف به همان پنجره‌ای نسبت داده می‌شود که از آن ساخته شده، و
    برچسبش هم نام واقعی ماه است. نتیجه: نمودار محاسبه‌شده و جدول اعلام‌شده
    روی هم می‌افتند — همان ادعای بازتولیدپذیری که صفحهٔ متدولوژی می‌کند.
    """
    if "date" not in frame.columns:
        return []
    dates = pd.to_datetime(frame["date"])
    rows = []
    for index, (name, start, end) in enumerate(JALALI_WINDOW):
        subset = frame[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
        if subset.empty:
            continue
        counts = _label_counts([str(code) for code in subset["label"]])
        rows.append({
            "month": index + 1,
            "title": name,
            "shares": _shares(counts),
            "counts": counts,
            "total": int(len(subset)),
        })
    return rows


def declared_trend(per_class: int = N_PER_CLASS) -> list[dict]:
    """ترکیب اعلام‌شدهٔ هر ماه — از توازن کلاس‌ها و وزن ماهانهٔ پیکربندی.

    دو چیز رو اینجا به هم گره خورده‌اند و نادیده‌گرفتن یکی، جدول را غلط می‌کند:

    * **توازن کلاس‌ها** — هر کلاس دقیقاً ``per_class`` نمونه می‌گیرد.
    * **وزن ماهانهٔ درون هر کلاس** — از ``MIX_BY_MONTH``.

    سهم هر کلاس *در یک ماه* حاصل تقسیم آندو است، نه خودِ وزن‌های جدول. یک بار
    وزن‌های جدول مستقیم به‌عنوان سهم ماهانه گزارش شد؛ نتیجه‌اش این شد که
    نمودار محاسبه‌شده هرگز با جدول اعلام‌شده نمی‌خواند — چون با ۶۰۰ نمونهٔ
    برابر در هر کلاس، سهم مثبت همواره از ۰٫۳۴ کمتر درمی‌آید. اینجا هر دو از
    *یک* تابع می‌آیند، پس اندازه‌گیری و اعلان ناچار روی هم می‌افتند.
    """
    counts = class_counts_per_month(per_class)
    rows = []
    for index, (name, _, _) in enumerate(JALALI_WINDOW):
        month_counts = {code: counts[code][index] for code in LABELS}
        rows.append({"month": index + 1, "title": name,
                     "counts": month_counts, "shares": _shares(month_counts),
                     "total": sum(month_counts.values())})
    return rows


def confidence_histogram(pipe, texts: list[str], bins: int = 10) -> list[tuple[float, int]]:
    """توزیع اطمینان پیش‌بینی‌ها.

    اگر مدل روی بیشتر نمونه‌ها اطمینان نزدیک ۱ بدهد، یعنی مدل *بی‌جهت*
    مطمئن است — نه این‌که حتماً درست می‌گوید. این نمودار برای دیدن همین است.
    """
    rows = predict_many(pipe, texts)
    if not rows:
        return []
    values = np.array([row["confidence"] for row in rows])
    edges = np.linspace(0.0, 1.0, bins + 1)
    counts, _ = np.histogram(values, bins=edges)
    step = 1.0 / bins
    return [(round(edge * 100, 1), int(count))
            for edge, count in zip(edges[:-1] + step / 2, counts)]


def length_histogram(frame: pd.DataFrame, bins: int = 12) -> list[tuple[float, int]]:
    """توزیع طول کامنت‌ها بر پایهٔ شمار توکن معنادار."""
    lengths = [len(tokenize(text)) for text in frame["text"]]
    lengths = [value for value in lengths if value > 0]
    if not lengths:
        return []
    top = max(lengths)
    step = max(1, int(np.ceil(top / bins)))
    edges = np.arange(0, top + step + 1, step)
    counts, _ = np.histogram(lengths, bins=edges)
    return [(float(edge), int(count)) for edge, count in zip(edges[:-1], counts)]


def class_terms(pipe, k: int = 8) -> dict[str, list[dict]]:
    """واژگان متمایزکنندهٔ هر کلاس — از ضرایب خود مدل."""
    out: dict[str, list[dict]] = {}
    for code in LABELS:
        pairs = top_terms(pipe, code, k=k)
        strongest = max((abs(score) for _, score in pairs), default=1.0) or 1.0
        out[code] = [{
            "term": term,
            "score": round(score, 3),
            "share": round(abs(score) / strongest, 3),
        } for term, score in pairs]
    return out


def unknown_terms(frame: pd.DataFrame, pipe, k: int = 10) -> list[dict]:
    """پرتکرارترین توکن‌هایی که در واژگان مدل نیستند.

    این فهرست، نقشهٔ راه بهبود مدل است: هر واژه‌ای که اینجا بالاست، برای مدل
    نامرئی است و اگر بار احساسی داشته باشد، مدل بخشی از سیگنال متن را از دست
    می‌دهد.
    """
    known = vocabulary(pipe)
    counter: Counter[str] = Counter()
    for text in frame["text"]:
        for token in tokenize(text):
            bare = token.lstrip("نـ")
            if bare not in known:
                counter[bare] += 1
    total = sum(counter.values()) or 1
    return [{"term": term, "count": int(count),
             "share": round(count / total, 4)}
            for term, count in counter.most_common(k)]


def summary(frame: pd.DataFrame, pipe, metrics: dict) -> dict:
    """عددهای خام شاخص‌های بالای صفحهٔ «تحلیل».

    این تابع عمداً هیچ قالب‌بندی‌ای انجام نمی‌دهد: عدد پایتونی برمی‌گرداند تا
    تصمیم دربارهٔ رقم و جداکننده در لایهٔ نمایش گرفته شود. اگر همین‌جا رشتهٔ
    آماده ساخته شود، هر مصرف‌کنندهٔ دیگری هم مجبور است همان قالب را بپذیرد.
    """
    lengths = [len(tokenize(text)) for text in frame["text"]]
    lengths = [value for value in lengths if value > 0]
    return {
        "n_samples": int(len(frame)),
        "vocabulary_size": int(metrics["vocabulary_size"]),
        "mean_length": round(float(np.mean(lengths)), 1) if lengths else 0.0,
        "class_count": len(LABELS),
    }
