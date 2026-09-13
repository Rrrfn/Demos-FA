# -*- coding: utf-8 -*-
"""دیتاست کامنت فارسی سه‌وجهی — قطعه‌جمله‌های واقع‌گرایانه + نویز کنترل‌شده.

دیتاست **سینتتیک** است. هیچ کامنت واقعی کاربری در آن نیست. ساخته می‌شود از
ترکیب قطعه‌جمله‌های دست‌نویس و چند منبع نویز که همهٔ آن‌ها صریح و قابل بازتولیدند:

* **نویز صفحه‌کلید عربی** — حروف فارسی با شکل عربی نوشته می‌شوند
  (``ی``→``ي``/``ى``، ``ک``→``ك``، ``ه``→``ة``). این رایج‌ترین ناهمگونی متن
  فارسی است. منبعش ``ARABIC_VARIANTS`` در ``normalize`` است — همان جدولی که
  نرمال‌ساز می‌شناسد، پس این نویز *بازیابی‌شدنی* است.
* **غلط تایپی** — از جدول ``TYPOS`` همان ماژول.
* **ایموجی** — پیشوند/پسوند احساسی.
* **جملهٔ مقابل** — ۲۵٪ نمونه‌ها یک قطعه از کلاس دیگر هم دارند (ابهام واقعی).
* **متن مخلوط فارسی/انگلیسی** — بخشی از نمونه‌ها واژهٔ انگلیسی دارند.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
روند درون دیتاست
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

دیتاست یک ستون ``date`` دارد و سهم کلاس‌ها ماه‌به‌ماه تغییر می‌کند. این تغییر
از جدول صریح ``MIX_BY_MONTH`` در ``config`` می‌آید — یعنی **هر چیزی که در
نمودار روند دیده می‌شود، همان چیزی است که در آن جدول نوشته شده**. این روند
ادعایی دربارهٔ بازار واقعی نیست؛ صفتی از خود دیتاست نمونه است و در صفحهٔ
متدولوژی و زیر خودِ نمودار هم همین‌طور گفته شده.
"""
from __future__ import annotations

import os
import random

import pandas as pd

from .config import (MIX_BY_MONTH, N_PER_CLASS, RANDOM_SEED, TREND_MONTHS,
                     dataset_path)
from .normalize import ARABIC_VARIANTS, TYPOS

POS = [
    "عالی بود", "خیلی خوب بود", "کیفیت فوق‌العاده", "ارسال سریع", "پشتیبانی عالی",
    "ممنون از فروشنده", "دقیقا همون چیزی بود که می‌خواستم", "قیمت مناسب",
    "بسته‌بندی تمیز", "پیشنهاد می‌کنم", "بهتر از انتظارم", "کیفیت ساخت درجه یک",
    "بسیار راضی هستم", "از خرید کاملا راضی", "سرعت ارسالش بی‌نظیر بود",
    "ارزش خرید داشت", "دوباره می‌خرم", "رنگش دقیقا مثل عکس بود",
    "برای این قیمت واقعا حرف نداره", "قیمتش نسبت به کیفیت منصفانه",
    "ارسال بموقع رسید", "بسته‌بندی حرفه‌ای و تمیز", "خوبه می‌ارزه",
    "سایزش درست بود", "جنسش محکمه", "کیفیت دوختش عالیه", "خیلی سریع رسید",
    # ساخت‌های نفی — نفی یک نکتهٔ منفی، نتیجهٔ مثبت می‌دهد. بدون این قطعه‌ها مدل
    # الگوی «نـ...» را یاد نمی‌گیرد و «بد نبود» را منفی می‌خواند.
    "بد نبود", "مشکلی نداشت", "ناراضی نبودم", "تأخیری نداشت",
    "ایرادی نگرفتم", "پشیمون نشدم", "کم نداشت", "سرش کلاه نرفتم",
]
NEG = [
    "بد بود", "کیفیت افتضاح", "دیر رسید", "پشتیبانی جواب نمی‌ده", "پشیمون شدم",
    "خراب رسید", "با عکس فرق داشت", "پولم پس داده نشد", "ارزش قیمتش رو نداره",
    "توصیه نمی‌کنم", "بعد از یک هفته از کار افتاد", "جنس فیک بود",
    "رنگش با عکس زمین تا آسمون فرق داشت", "اصلا مثل توضیحات نبود",
    "بسته‌بندی پاره رسیده بود", "خیلی ناراضی هستم", "حیف پول و وقت",
    "برنگشته پولم", "برند تقلبی بود", "از این خرید بشدت پشیمونم",
    "قیمتش با این کیفیت بی‌معنی", "ارسالش هفته طول کشید",
    "کیفیتش افت کرده نسبت به قبل", "دو بار شکسته تحویل دادن", "گارانتی الکی بود",
    # ساخت‌های نفی — نفی یک نکتهٔ مثبت، نتیجهٔ منفی می‌دهد.
    "خوب نبود", "راضی نبودم", "کیفیت نداشت", "به کار نمی‌آد",
    "ارزش نداشت", "جواب نداد", "انتظارم رو برآورده نکرد", "درست نشد",
]
NEU = [
    "بسته رسید", "طبق توضیحات", "قیمتش متوسطه", "باید تست کنم", "هفته بعد نظر می‌دم",
    "معمولی بود", "همون بود که سفارش دادم", "ارسال شد", "در حال استفاده هستم",
    "سوال داشتم پشتیبانی پاسخ داد", "تا الان مشکلی نداشته", "قابل قبول",
    "متوسط به بالا", "به زودی نظر دقیق می‌دم", "بستگی به استفاده داره",
    "چیز خاصی نداره", "عادی بود", "قیمتش رو فعلا نمی‌دونم",
    "ارسال ظهر امروز انجام شد", "بسته‌بندی استاندارد بود", "هنوز بازش نکردم",
    "اندازه‌اش معمولیه", "دو تا سفارش دادم یکیش رسید",
    # نفی بدون بار احساسی — خنثی می‌ماند.
    "نظری ندارم", "فرقی نمی‌کنه", "مشکلی ندیدم", "تست نکردم",
    "عوض نشده", "تفاوتی نداشت",
]

#: نمونه‌های مخلوط فارسی/انگلیسی. واژه‌های انگلیسی اینجا همان‌هایی هستند که
#: در کامنت واقعی محصول دیده می‌شوند (نام ویژگی، وضعیت ارسال).
POS_MIXED = [
    "quality عالی بود و shipping سریع",
    "پنل display شفافه و battery خوبه",
    "بسته packaging حرفه‌ای بود، good بود",
    "size دقیقا درست، value for money داره",
]
NEG_MIXED = [
    "quality بد بود و shipping خیلی دیر",
    "battery افتضاحه، display خط افتاده",
    "packaging پاره بود، bad بود",
    "size اشتباه، refund هم ندادن",
]
NEU_MIXED = [
    "shipping معمولی بود، quality متوسط",
    "display رو باید تست کنم، battery نمی‌دونم",
    "size در حد معمول، packaging استاندارد",
]

PREFIX = ["سلام، ", "بچه‌ها ", "آقا این ", "وای ", "خب ", "راستش ", ""]

# ------------------------------------------------------------------ ایموجی
#: ایموجی‌ها **به تفکیک کلاس** اضافه می‌شوند، نه به‌عنوان نویز مشترک.
#:
#: این تصمیم از یک اشکال واقعی آمده است: وقتی یک فهرست مشترک به همهٔ کلاس‌ها
#: اضافه شود، ایموجی در هر سه کلاس تقریباً به یک اندازه دیده می‌شود و مدل هیچ
#: چیزی از آن یاد نمی‌گیرد — یعنی متنی که فقط «❤️💯» است، بی‌سیگنال می‌ماند،
#: در حالی که ``normalize.EMOJI_LEXICON`` همین ایموجی‌ها را به «عالی» و «خوب»
#: نگاشته است. الان ایموجی همان چیزی است که آن جدول وعده می‌دهد: نشانهٔ احساس.
#:
#: نشانه‌های نگارشی (``!``، ``؟``، `` ...``) هنوز برای همه مشترک‌اند، چون واقعاً
#: به کلاس کاری ندارند.
SUFFIX_POS = [" 👍", " 😊", " 💯", " 🔥", " ❤️", ""]
SUFFIX_NEG = [" 🙁", " 👎", " 💔", " 😡", ""]
SUFFIX_NEU = [" 😐", " 🤔", ""]
SUFFIX_PUNCT = ["!", "؟", " ...", "", "", ""]

SUFFIX_BY_LABEL: dict[str, list[str]] = {
    "pos": SUFFIX_POS,
    "neg": SUFFIX_NEG,
    "neu": SUFFIX_NEU,
}

#: برای سازگاری با کدی که فهرست کامل را می‌خواهد.
SUFFIX = SUFFIX_POS + SUFFIX_NEG + SUFFIX_NEU + SUFFIX_PUNCT

BANKS: dict[str, list[str]] = {
    "pos": POS + POS_MIXED,
    "neg": NEG + NEG_MIXED,
    "neu": NEU + NEU_MIXED,
}

# ------------------------------------------------------------------ پنجرهٔ زمانی
#: پنجرهٔ ثابت دیتاست نمونه: نیمهٔ نخست ۱۴۰۴.
#:
#: این یک **نگاشت ثابت** است، نه تبدیل تقویم عمومی. برای نمودار روند همین کافی
#: است و هیچ ادعای تقویمی دیگری نمی‌کند. طول هر بازه ۳۱ روز است، پس ماه‌ها
#: هم‌اندازه‌اند و روند نمودار را کج نمی‌کنند.
JALALI_WINDOW: tuple[tuple[str, str, str], ...] = (
    ("فروردین", "2025-03-21", "2025-04-20"),
    ("اردیبهشت", "2025-04-21", "2025-05-21"),
    ("خرداد", "2025-05-22", "2025-06-21"),
    ("تیر", "2025-06-22", "2025-07-22"),
    ("مرداد", "2025-07-23", "2025-08-22"),
    ("شهریور", "2025-08-23", "2025-09-22"),
)

MONTH_NAMES: tuple[str, ...] = tuple(name for name, _, _ in JALALI_WINDOW)


def month_share(label: str) -> list[float]:
    """سهم هر ماه از نمونه‌های یک کلاس — از جدول ``MIX_BY_MONTH``."""
    weights = [float(MIX_BY_MONTH[index][label]) for index in range(TREND_MONTHS)]
    total = sum(weights) or 1.0
    return [weight / total for weight in weights]


def class_counts_per_month(n_per_class: int = N_PER_CLASS) -> dict[str, list[int]]:
    """شمار نمونهٔ هر کلاس در هر ماه — با جمع دقیقاً ``n_per_class``.

    تقسیم ساده اعشار تولید می‌کند؛ باقی‌مانده به آخرین ماه ریخته می‌شود تا
    توازن کلاس‌ها دقیق بماند و آزمون‌های توازن بشکنند.
    """
    counts: dict[str, list[int]] = {}
    for label in BANKS:
        shares = month_share(label)
        row = [int(round(n_per_class * share)) for share in shares]
        row[-1] += n_per_class - sum(row)
        counts[label] = row
    return counts


def _random_date(month_index: int, rng: random.Random) -> str:
    """یک روز تصادفی داخل ماه — با نگاشت ثابت پنجره."""
    import datetime

    _, start, _ = JALALI_WINDOW[month_index]
    base = datetime.date.fromisoformat(start)
    return (base + datetime.timedelta(days=rng.randrange(31))).isoformat()


def _noise(text: str, rng: random.Random) -> str:
    """نویز واقع‌گرایانه: صفحه‌کلید عربی + غلط تایپی."""
    if rng.random() < 0.30:
        # تایپ با صفحه‌کلید عربی — چند حرف، نه همه
        for char, variants in ARABIC_VARIANTS.items():
            if char in text and rng.random() < 0.5:
                text = text.replace(char, rng.choice(variants), 1)
    if rng.random() < 0.15:
        candidates = [(w, c) for w, c in TYPOS.items() if c in text]
        if candidates:
            wrong, correct = rng.choice(candidates)
            text = text.replace(correct, wrong, 1)
    return text


def _compose(fragments: list[str], label: str, rng: random.Random) -> str:
    k = rng.randint(1, 3)
    parts = rng.sample(fragments, min(k, len(fragments)))
    # بند تقابل — کمی از نمونه‌ها یک قطعه از کلاس دیگر هم دارند (ابهام واقعی)
    if rng.random() < 0.25:
        other = rng.choice([b for b in BANKS if b != label])
        joiner = "ولی " if rng.random() < 0.5 else "با این حال "
        parts.append(joiner + rng.choice(BANKS[other]))
    tail = rng.choice(SUFFIX_BY_LABEL.get(label, SUFFIX_NEU)) + rng.choice(SUFFIX_PUNCT)
    text = rng.choice(PREFIX) + rng.choice(["، ", " "]).join(parts) + tail
    return _noise(text, rng)


def generate(n_per_class: int = N_PER_CLASS, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """ساخت دیتاست با توازن دقیق کلاس‌ها و روند ماهانهٔ صریح."""
    rng = random.Random(seed)
    counts = class_counts_per_month(n_per_class)
    rows: list[dict] = []
    for month_index in range(TREND_MONTHS):
        for label, fragments in BANKS.items():
            needed = counts[label][month_index]
            seen: set[str] = set()
            made = 0
            attempts = 0
            while made < needed and attempts < needed * 60:
                attempts += 1
                text = _compose(fragments, label, rng)
                if text in seen:
                    continue
                seen.add(text)
                # برای حجم‌های بزرگ، تکرار متن اجتناب‌ناپذیر است؛ پس از
                # تلاش‌های بی‌نتیجه، یک پسوند یکتا اضافه می‌شود تا کلید تکراری نشود.
                if attempts > needed * 20:
                    text = f"{text} ({made})"
                rows.append({"text": text, "label": label,
                             "date": _random_date(month_index, rng)})
                made += 1
    frame = pd.DataFrame(rows)
    frame = frame.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return frame[["text", "label", "date"]]


def get_dataset(force: bool = False) -> pd.DataFrame:
    """دیتاست با کش روی دیسک."""
    path = dataset_path()
    if force or not os.path.exists(path):
        frame = generate()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        frame.to_csv(path, index=False)
        return frame
    return pd.read_csv(path)
