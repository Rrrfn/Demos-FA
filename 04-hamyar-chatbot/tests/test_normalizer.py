# -*- coding: utf-8 -*-
"""Normalization and tokenization — the foundation of every match."""
from __future__ import annotations

import pytest

from app.nlp import content_tokens, normalize, tokenize
from app.nlp.normalizer import digits_to_persian, has_letters


class TestNormalize:
    """Canonical form used for both the corpus and the query."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("كيفيت", "کیفیت"),                    # Arabic kaf + yeh
            ("Arabic ي here", "arabic ی here"),
            ("مُعَلِّم", "معلم"),                   # diacritics removed
            ("می‌خواهم", "می خواهم"),               # ZWNJ → space
            ("سلام   دنیا", "سلام دنیا"),            # whitespace collapsed
            ("سلام!", "سلام"),                      # punctuation dropped
            ("«تست»", "تست"),
            ("۱۲۳", "123"),                         # Persian digits
            ("٤٥٦", "456"),                         # Arabic-Indic digits
            ("هزینهٔ ارسال", "هزینه ارسال"),        # hamza mark dropped
            ("  ", ""),
            ("", ""),
        ],
    )
    def test_normalization(self, raw, expected):
        assert normalize(raw) == expected

    def test_none_is_safe(self):
        assert normalize(None) == ""

    def test_idempotent(self):
        once = normalize("می‌خواهم كیفیت ۱۲۳ را بدانم!")
        assert normalize(once) == once

    def test_kashida_removed(self):
        assert normalize("ســـلام") == "سلام"

    def test_has_letters(self):
        assert has_letters("سلام") is True
        assert has_letters("123") is False

    def test_persian_digits_helper(self):
        assert digits_to_persian(2026) == "۲۰۲۶"


class TestTokenize:
    """Tokenization feeds TF-IDF, so its behaviour is part of the contract."""

    def test_basic_split(self):
        assert tokenize("سفارش من کجاست؟") == ["سفارش", "من", "کجاست"]

    def test_tokens_are_normalized(self):
        assert tokenize("كيفيت ۱۲") == ["کیفیت", "12"]

    def test_content_tokens_drop_stopwords(self):
        tokens = content_tokens("کتاب از فروشگاه برای من")
        assert "از" not in tokens and "برای" not in tokens
        assert "فروشگاه" in tokens

    def test_content_tokens_drop_letterless_tokens(self):
        assert content_tokens("۱۲۳ --- !!!") == []

    def test_content_tokens_keep_mixed_terms(self):
        # Latin identifiers such as 2FA or B2B must survive for mixed queries.
        assert "2fa" in content_tokens("ورود 2FA دارید؟")

    def test_empty_input(self):
        assert content_tokens("") == []
        assert content_tokens(None) == []
