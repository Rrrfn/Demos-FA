# -*- coding: utf-8 -*-
"""برچسب‌های فارسی و قالب‌بندی اعداد.

همهٔ متنی که به کاربر می‌رسد از اینجا می‌آید تا هیچ‌جا برچسب خام انگلیسی
(``pos`` / ``neu`` / ``neg``) در رابط دیده نشود و رقم‌ها یکدست فارسی باشند.
"""
from __future__ import annotations

from .config import CONFIDENCE_HIGH, CONFIDENCE_LOW, LABEL_EMOJI, LABEL_FA


def to_persian_digits(value: object) -> str:
    """تبدیل رقم‌های لاتین به فارسی — برای نمایش در رابط."""
    table = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return str(value).translate(table)


def fa_number(value: float | int, *, decimals: int = 0) -> str:
    """عدد با جداکنندهٔ هزارگان فارسی.

    جداکنندهٔ هزارگان ``٬`` و ممیز ``٫`` است. اگر ممیز لاتین بماند، در متن
    فارسی هم ناهمخوان است و هم با جداکنندهٔ هزارگان اشتباه گرفته می‌شود.
    """
    if decimals:
        text = f"{value:,.{decimals}f}"
    else:
        text = f"{int(round(value)):,}"
    return (text.replace(",", "٬").replace(".", "٫")
            .translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))


def fa_percent(ratio: float, *, decimals: int = 1, signed: bool = False) -> str:
    """درصد فارسی؛ ``signed`` علامت مثبت/منفی را هم نشان می‌دهد."""
    sign = ""
    if signed:
        sign = "−" if ratio < 0 else "+"
    return f"{sign}{fa_number(abs(ratio) * 100, decimals=decimals)}٪"


def fa_datetime(value: object) -> str:
    """مهر زمانی با رقم فارسی — ذخیره لاتین است، نمایش فارسی."""
    return to_persian_digits(value if value not in (None, "") else "—")


def sentiment_label(code: str) -> str:
    return LABEL_FA.get(code, code)


def sentiment_label_full(code: str) -> str:
    """برچسب با نشانهٔ تصویری — برای جایی که رنگ تنها حامل معنا نباشد."""
    return f"{LABEL_FA.get(code, code)} {LABEL_EMOJI.get(code, '')}".strip()


# ------------------------------------------------------------------ باند اطمینان
#: واژگان باند. عمداً از «بالا/متوسط/پایین» استفاده نمی‌کنیم: آن‌ها دربارهٔ
#: *خودِ اطمینان* حرف می‌زنند، نه دربارهٔ این‌که کاربر باید به عدد اعتماد کند
#: یا نه. «قابل اتکا / مرزی / نامطمئن» همان چیزی است که به تصمیم کاربر مربوط است.
BAND_FA = {
    "high": "قابل اتکا",
    "medium": "مرزی",
    "low": "نامطمئن",
}

BAND_HINT = {
    "high": "مدل روی این متن نظر مشخصی دارد.",
    "medium": "نتیجه نزدیک مرز است؛ با احتیاط بخوانید.",
    "low": "مدل بین دو حالت مانده؛ این برچسب را قطعی نگیرید.",
}


def confidence_band(confidence: float) -> str:
    """باند اطمینان از روی احتمالِ برچسبِ برنده."""
    value = float(confidence)
    if value >= CONFIDENCE_HIGH:
        return "high"
    if value >= CONFIDENCE_LOW:
        return "medium"
    return "low"


def band_label(band: str) -> str:
    return BAND_FA.get(band, band)


def band_css(band: str) -> str:
    return {"high": "band-high", "medium": "band-medium", "low": "band-low"}.get(band, "")


def verdict_sentence(code: str, confidence: float, band: str) -> str:
    """یک جملهٔ صادقانه دربارهٔ نتیجه — بدون ادعای قطعیت.

    این جمله عمداً در یک جا ساخته می‌شود: هم صفحهٔ تحلیل و هم خروجی گروهی و
    هم API همان را می‌گویند.
    """
    label = sentiment_label(code)
    percent = fa_percent(confidence, decimals=0)
    if band == "high":
        return f"نظر مدل «{label}» است و با اطمینان {percent} روی این متن می‌ایستد."
    if band == "medium":
        return (f"نظر مدل «{label}» است، ولی اطمینان {percent} مرزی است — "
                f"این متن بین دو حالت می‌ماند.")
    return (f"مدل به «{label}» تمایل دارد (اطمینان {percent})، ولی این متن "
            f"سیگنال روشنی ندارد؛ برچسب را قطعی نگیرید.")


def sentiment_slug(code: str) -> str:
    """نام کلاس برای استفاده در نام فایل خروجی — فقط لاتین."""
    return {"pos": "positive", "neu": "neutral", "neg": "negative"}.get(code, code)
