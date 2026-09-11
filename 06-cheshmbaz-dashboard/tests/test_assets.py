# -*- coding: utf-8 -*-
"""آزمون رجیستری دارایی‌ها — یکدستی، جستجو و ناشناخته‌ها."""
from __future__ import annotations

import pytest

from cheshmbaz import assets
from cheshmbaz.core.errors import UnknownAsset
from cheshmbaz.core.models import AssetKind


def test_registry_is_internally_consistent():
    """شناسه‌ها یکتا، عنوان‌ها پر، کلید منبع مشخص و واحدها معتبر."""
    slugs = [asset.slug for asset in assets.ALL_ASSETS]
    assert len(slugs) == len(set(slugs)), "شناسهٔ تکراری در رجیستری"

    for asset in assets.ALL_ASSETS:
        assert asset.title.strip(), f"عنوان خالی برای {asset.slug}"
        assert asset.provider in {"tgju", "coingecko"}, asset.slug
        assert asset.unit in {"toman", "usd"}, asset.slug
        assert asset.precision >= 0, asset.slug
        if asset.is_crypto:
            assert asset.provider == "coingecko"
            assert asset.unit == "usd"
        else:
            assert asset.provider == "tgju"
            assert asset.unit == "toman"


def test_required_coverage_is_present():
    """حداقل پوشش خواسته‌شده: طلا، سکه، دلار، یورو، بیت‌کوین، اتریوم."""
    for slug in ("geram18", "sekee", "usd", "eur", "bitcoin", "ethereum"):
        assert assets.exists(slug), slug

    kinds = {asset.kind for asset in assets.ALL_ASSETS}
    assert kinds == {AssetKind.GOLD, AssetKind.COIN, AssetKind.CURRENCY, AssetKind.CRYPTO}
    assert len(assets.by_kind(AssetKind.CRYPTO)) >= 5


def test_ordering_is_stable_and_grouped():
    ordered = assets.all_assets_ordered()
    kinds = [asset.kind.order for asset in ordered]
    assert kinds == sorted(kinds)
    assert [asset.slug for asset in ordered] == [asset.slug for asset in assets.all_assets_ordered()]


def test_provider_partition_covers_everything():
    tgju = {asset.slug for asset in assets.by_provider("tgju")}
    coingecko = {asset.slug for asset in assets.by_provider("coingecko")}
    assert tgju | coingecko == set(assets.ASSETS)
    assert not tgju & coingecko


def test_get_returns_asset_and_raises_for_unknown():
    assert assets.get("usd").title == "دلار آمریکا"
    with pytest.raises(UnknownAsset) as error:
        assets.get("no-such-asset")
    assert "no-such-asset" in error.value.message


@pytest.mark.parametrize(
    "query,expected",
    [
        ("دلار", "usd"),
        ("دلار آمریکا", "usd"),
        ("سکه", "sekee"),
        ("امامی", "sekee"),
        ("طلای ۱۸ عیار", "geram18"),
        ("btc", "bitcoin"),
        ("USDT", "tether"),
        ("بیت کوین", "bitcoin"),
        ("یورو", "eur"),
    ],
)
def test_search_resolves_aliases_and_titles(query, expected):
    found = assets.search(query)
    assert found is not None, query
    assert found.slug == expected


def test_search_handles_arabic_characters_and_noise():
    """ی/ک عربی و فاصله‌های اضافه باید به همان دارایی برسند."""
    assert assets.search("دلار  امريكا").slug == "usd"
    assert assets.search("  سكه  ").slug == "sekee"
    assert assets.search("") is None
    assert assets.search("چیزی که نیست") is None


def test_featured_assets_exist():
    for slug in assets.FEATURED:
        assert slug in assets.ASSETS, slug
