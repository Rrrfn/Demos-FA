# -*- coding: utf-8 -*-
"""آزمون ساخت دیتاست نمونه.

دیتاست سینتتیک است، ولی ساختش نباید دلبخواه باشد: توازن کلاس‌ها، تکرارپذیری،
وجود نویز و — مهم‌تر از همه — **وابستگی ایموجی به کلاس** آزموده می‌شود. آن
وابستگی از یک اشکال واقعی آمده: ایموجی به‌عنوان نویز مشترک به هر سه کلاس
اضافه می‌شد و در نتیجه مدل از آن هیچ سیگنالی یاد نمی‌گرفت.
"""
from __future__ import annotations

from hassanj.config import TREND_MONTHS
from hassanj.dataset import (BANKS, JALALI_WINDOW, SUFFIX_BY_LABEL,
                             class_counts_per_month, generate, get_dataset,
                             month_share)
from hassanj.normalize import tokenize


def test_shape_and_exact_balance():
    frame = generate(n_per_class=60, seed=3)
    assert len(frame) == 180
    counts = frame["label"].value_counts().to_dict()
    assert counts == {"pos": 60, "neu": 60, "neg": 60}


def test_columns_and_index():
    frame = generate(n_per_class=40, seed=5)
    assert list(frame.columns) == ["text", "label", "date"]
    assert frame.index.tolist() == list(range(len(frame)))


def test_reproducible_with_same_seed():
    assert generate(n_per_class=50, seed=11).equals(generate(n_per_class=50, seed=11))
    assert not generate(n_per_class=50, seed=11).equals(
        generate(n_per_class=50, seed=12))


def test_dates_stay_inside_the_declared_window():
    """هیچ تاریخی نباید از پنجرهٔ ثابت اعلام‌شده بیرون بزند.

    پنجره‌ها با تاریخ میلادی نوشته شده‌اند و مرزهایشان با ماه میلادی یکی
    نیست؛ پس سنجش روی خود بازه‌های پنجره انجام می‌شود، نه روی شمار ماه‌ها.
    """
    frame = generate(n_per_class=90, seed=2)
    assert frame["date"].min() >= JALALI_WINDOW[0][1]
    assert frame["date"].max() <= JALALI_WINDOW[-1][2]
    for _, start, end in JALALI_WINDOW:
        window = frame[(frame["date"] >= start) & (frame["date"] <= end)]
        assert len(window) > 0


def test_month_shares_follow_declared_table():
    """سهم محاسبه‌شدهٔ هر ماه باید همان ``month_share`` باشد و جمعش دقیق بماند.

    وزن‌های جدول نسبی‌اند و پیش از تقسیم نرمال می‌شوند؛ پس سنجش با همان تابع
    انجام می‌شود تا آزمون، خودِ قاعده را بسنجد نه یک بازنویسی دوباره از آن.
    """
    counts = class_counts_per_month(600)
    for code in ("pos", "neu", "neg"):
        total = sum(counts[code])
        assert total == 600                     # توازن کلاس‌ها دقیق می‌ماند
        shares = month_share(code)
        assert abs(sum(shares) - 1.0) < 1e-9
        for index in range(TREND_MONTHS):
            assert abs(counts[code][index] / total - shares[index]) <= 0.01


def test_trend_is_monotonic_for_positive_class():
    """روند اعلام‌شده یکنواخت است: سهم مثبت ماه‌به‌ماه بالا می‌رود.

    اگر این‌طور نباشد، نمودار «روند» صفحهٔ تحلیل چیزی نشان می‌دهد که جدول
    اعلام‌شده نمی‌گوید و ادعای بازتولیدپذیری می‌شکند.
    """
    shares = month_share("pos")
    assert shares == sorted(shares)
    assert shares[-1] > shares[0]


def test_typo_and_arabic_noise_present_and_repairable():
    frame = generate(n_per_class=200, seed=2)
    joined = " ".join(frame["text"])
    assert "ي" in joined or "ك" in joined          # نویز صفحه‌کلید عربی
    assert "خوب" in joined
    # نویز باید بازیافت‌شدنی باشد: پس از نرمال‌سازی هیچ حرف عربی نماند.
    from hassanj.normalize import normalize

    assert "ي" not in normalize(joined)


def test_emoji_carry_class_signal():
    """ایموجی مثبت باید در متن‌های مثبت بیاید، نه در همهٔ کلاس‌ها.

    این آزمون رگرسیونِ همان اشکالی است که یک بار پیدا و اصلاح شد.
    """
    frame = generate(n_per_class=400, seed=4)
    positive_mark = frame["text"].str.contains("👍|😊|💯|🔥|❤️", regex=True)
    negative_mark = frame["text"].str.contains("🙁|👎|💔|😡", regex=True)

    pos_with_positive = ((frame["label"] == "pos") & positive_mark).sum()
    neg_with_positive = ((frame["label"] == "neg") & positive_mark).sum()
    neg_with_negative = ((frame["label"] == "neg") & negative_mark).sum()
    pos_with_negative = ((frame["label"] == "pos") & negative_mark).sum()

    assert pos_with_positive > 0 and neg_with_negative > 0
    assert neg_with_positive == 0 and pos_with_negative == 0


def test_emoji_suffix_lists_are_disjoint():
    """پسوندهای احساسی هر کلاس باید از هم جدا باشند.

    رشتهٔ خالی عمداً در هر سه فهرست هست (گزینهٔ «بدون ایموجی») و از سنجش
    کنار گذاشته می‌شود.
    """
    positive = {item for item in SUFFIX_BY_LABEL["pos"] if item.strip()}
    negative = {item for item in SUFFIX_BY_LABEL["neg"] if item.strip()}
    neutral = {item for item in SUFFIX_BY_LABEL["neu"] if item.strip()}
    assert positive and negative and neutral
    assert not positive & negative
    assert not positive & neutral
    assert not negative & neutral

    #: هر ایموجی باید در جدول نگاشت نرمال‌ساز هم باشد؛ وگرنه در متن پاک می‌شود
    #: و سیگنالش به مدل نمی‌رسد.
    from hassanj.normalize import EMOJI_LEXICON

    for emoji in positive | negative | neutral:
        assert emoji.strip() in EMOJI_LEXICON


def test_banks_cover_all_labels():
    assert set(BANKS) == {"pos", "neg", "neu"}
    for fragments in BANKS.values():
        assert len(fragments) >= 20


def test_texts_are_tokenisable_and_not_empty():
    frame = generate(n_per_class=30, seed=9)
    assert not frame["text"].str.strip().eq("").any()
    assert all(tokenize(text) for text in frame["text"])


def test_cached_dataset_round_trips(fast_env):
    frame = get_dataset()
    assert list(frame.columns) == ["text", "label", "date"]
    assert len(frame) == len(fast_env["frame"])
