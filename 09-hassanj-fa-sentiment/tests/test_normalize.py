# -*- coding: utf-8 -*-
"""آزمون نرمال‌سازی فارسی — دقیقاً همان مواردی که در متن پروژه فهرست شده‌اند:
حروف عربی و فارسی، نیم‌فاصله، علائم، ایموجی، غلط تایپی، متن مخلوط، خالی و بلند.
"""
from __future__ import annotations

import pytest

from hassanj.normalize import (ARABIC_VARIANTS, NEG_TAG, TYPOS, clean, normalize,
                               repair, tokenize)

# ------------------------------------------------------------ حروف عربی/فارسی
@pytest.mark.parametrize("raw,expected", [
    ("كتاب يوسف", "کتاب یوسف"),          # ک و ی عربی
    ("مسئوليت", "مسئولیت"),               # ی عربی در واژهٔ دارای ئ
    ("خانة من", "خانه من"),               # ة عربی
    ("ىكى", "یکی"),                       # ی مقصور و ک عربی
])
def test_arabic_letters_become_persian(raw, expected):
    assert normalize(raw) == expected


def test_every_arabic_variant_is_reachable():
    """هر شکل عربیِ جدول باید پس از نرمال‌سازی به شکل فارسی برسد."""
    for persian, variants in ARABIC_VARIANTS.items():
        for variant in variants:
            assert normalize(f"ا{variant}ا") == f"ا{persian}ا"


def test_hamza_not_collapsed_into_yeh():
    """``ئ`` نباید به ``ی`` تبدیل شود؛ وگرنه «مسئولیت» به واژهٔ بی‌معنا بدل می‌شود."""
    assert normalize("مسئولیت") == "مسئولیت"
    assert "مسيوليت" != normalize("مسئولیت")


# ------------------------------------------------------------------ نیم‌فاصله
def test_half_space_preserved():
    assert "\u200c" in normalize("می‌خواهم")
    assert normalize("می‌خواهم") == "می‌خواهم"


def test_half_space_is_split_into_two_tokens():
    """TF-IDF روی توکن کار می‌کند، پس ``می‌خواهم`` دو توکن می‌شود.

    اگر چسبیده بماند، هر فعل مضارع یک واژهٔ مستقل شمرده می‌شود و واژگان
    بی‌دلیل چند برابر می‌شود.
    """
    tokens = tokenize("من می‌خواهم بخرم")
    assert "خواهم" in tokens and "بخرم" in tokens
    assert not any("\u200c" in token for token in tokens)


# -------------------------------------------------------------------- اعراب
def test_diacritics_removed():
    assert normalize("مُثَبَّت") == "مثبت"


# --------------------------------------------------------------- تکرار حروف
@pytest.mark.parametrize("raw,expected", [
    ("سلفففففف", "سلف"),
    ("خییییییلی", "خیلی"),
])
def test_repeated_letters_collapsed(raw, expected):
    """سه تکرار یا بیشتر به یکی کاهش می‌یابد؛ دو تکرار واژهٔ واقعی فارسی است
    (مثل «ممنون») و دست‌نخورده می‌ماند."""
    assert normalize(raw) == expected


def test_double_letter_words_are_untouched():
    assert normalize("ممنون از خرید") == "ممنون از خرید"


def test_latin_words_are_not_collapsed():
    """کاهش تکرار حرف فقط داخل خط فارسی/عربی معنا دارد.

    رگرسیون: الگوی عام واژه‌های لاتین را خرد می‌کرد (``zzzz`` → ``z``) و
    توکن‌هایی مثل کد محصول یا نام برند را بی‌صدا خراب می‌کرد.
    """
    assert normalize("zzzz qqqq") == "zzzz qqqq"
    assert normalize("BUZZZZ") == "BUZZZZ"
    assert normalize("AAA-123") == "AAA 123"


# ------------------------------------------------------------ علائم نگارشی
def test_punctuation_removed_but_words_kept():
    result = normalize("عالی بود!!! واقعاً؟")
    assert "!" not in result and "؟" not in result
    assert "عالی" in result and "واقعا" in result


def test_url_and_mention_removed_before_emoji_mapping():
    result = normalize("سلام https://shop.ir/x @seller 👍")
    assert "http" not in result and "@seller" not in result
    assert "خوب" in result          # 👍 باید نگاشته شده باشد


# ------------------------------------------------------------------- ایموجی
def test_emoji_mapped_to_words():
    assert "عالی" in normalize("❤️")
    assert "بد" in normalize("😡")
    assert "خوب" in normalize("👍")


def test_neutral_emoji_do_not_create_signal():
    """ایموجی تزئینی نباید سیگنالی از خودش بسازد."""
    assert tokenize("✨🎁") == []


# ------------------------------------------------------------------- غلط تایپی
@pytest.mark.parametrize("wrong,right", [
    ("خريد", "خرید"), ("خيلی", "خیلی"), ("چيزي", "چیزی"),
])
def test_typos_repaired(wrong, right):
    """جدول غلط‌ها روی *شکل نرمال‌شدهٔ* واژه کار می‌کند، پس نرمال‌سازی اول است."""
    assert repair(normalize(wrong)) == right


def test_typo_table_is_one_source_of_truth():
    """هر ورودی جدول باید خودش را به شکل درست برساند و کلید≠مقدار باشد."""
    for wrong, right in TYPOS.items():
        assert wrong != right
        assert repair(normalize(wrong)) == right


# ------------------------------------------------------------ متن مرکب و لاتین
def test_mixed_persian_english_keeps_both():
    tokens = tokenize("quality خیلی خوب بود و shipping سریع")
    assert "shipping" in tokens and "quality" in tokens


def test_full_english_has_no_persian_tokens():
    """متن کامل انگلیسی توکن‌های خودش را می‌دهد — یعنی بیرون از دامنه است، نه خالی.

    همین تفاوت است که وضعیت ``out_of_domain`` را از ``no_signal`` جدا می‌کند.
    """
    tokens = tokenize("The delivery took longer than expected")
    assert tokens == ["The", "delivery", "took", "longer", "than", "expected"]
    assert all(all(ord(char) < 128 for char in token) for token in tokens)


# ------------------------------------------------------------------- علامت نفی
def test_negation_is_marked_on_following_token():
    tokens = tokenize("خوب نبود")
    assert any(token.startswith(NEG_TAG) for token in tokens)
    assert f"{NEG_TAG}خوب" in tokens


def test_negation_marker_distinguishes_opposite_sentences():
    """«ناراحت شدم» و «ناراحت نشدم» نباید یک بردار بدهند."""
    assert tokenize("ناراحت شدم") != tokenize("ناراحت نشدم")


# ------------------------------------------------------------------ حالت‌های مرزی
@pytest.mark.parametrize("value", ["", "   ", "\n\t", None, "!!! ... ؟"])
def test_empty_and_symbol_only_inputs(value):
    assert tokenize(value) == []
    assert normalize(value) == ""


def test_long_input_is_handled_without_error():
    text = "کیفیت عالی بود " * 2000
    assert len(normalize(text)) > 0
    assert len(tokenize(text)) > 0


def test_clean_is_stable_on_already_clean_text():
    once = clean("کیفیت عالی بود، ارسال سریع")
    assert clean(once) == once
