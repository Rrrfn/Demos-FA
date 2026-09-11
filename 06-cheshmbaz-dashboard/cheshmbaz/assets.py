# -*- coding: utf-8 -*-
"""رجیستری دارایی‌ها — تنها جایی که برای افزودن قلم تازه باید دست ببرید.

هر قلم یک ورودی است: شناسه‌اش در سامانه، عنوان فارسی، دسته، واحد و کلیدی که
در منبع داده باید خوانده شود. هیچ قیمتی این‌جا نیست: نه قیمت پایه، نه قیمت
پیش‌فرض. قیمت فقط از منبع زنده می‌آید.

افزودن قلم تازه:

    Asset("silver", "نقره", AssetKind.GOLD, provider_key="silver")

و بقیهٔ لایه‌ها (جمع‌آور، ذخیره‌سازی، نمودار، هشدار و API) خودکار آن را
می‌بینند، چون همه از همین رجیستری تغذیه می‌شوند.
"""
from __future__ import annotations

from .core.errors import UnknownAsset
from .core.models import Asset, AssetKind

# ---------------------------------------------------------------------------
# طلا و سکه و ارز از منبع داخلی (tgju) خوانده می‌شوند. طلا، سکه و ارز ریالی
# هستند و برای رسیدن به تومان بر ۱۰ تقسیم می‌شوند.
# ---------------------------------------------------------------------------
_ASSETS: tuple[Asset, ...] = (
    # ---------------------------------------------------------------- طلا
    Asset("geram18", "طلای ۱۸ عیار", AssetKind.GOLD, provider_key="geram18", symbol="GOLD18"),
    Asset("geram24", "طلای ۲۴ عیار", AssetKind.GOLD, provider_key="geram24", symbol="GOLD24"),
    Asset("mesghal", "مثقال طلا", AssetKind.GOLD, provider_key="mesghal", symbol="MESGHAL"),
    # ---------------------------------------------------------------- سکه
    Asset("sekee", "سکه امامی", AssetKind.COIN, provider_key="sekee", symbol="SEKEE"),
    Asset("sekeb", "سکه بهار آزادی", AssetKind.COIN, provider_key="sekeb", symbol="SEKEB"),
    Asset("nim", "نیم‌سکه", AssetKind.COIN, provider_key="nim", symbol="NIM"),
    Asset("rob", "ربع‌سکه", AssetKind.COIN, provider_key="rob", symbol="ROB"),
    Asset("gerami", "سکه گرمی", AssetKind.COIN, provider_key="gerami", symbol="GERAMI"),
    # ---------------------------------------------------------------- ارز
    Asset("usd", "دلار آمریکا", AssetKind.CURRENCY, provider_key="price_dollar_rl", symbol="USD"),
    Asset("eur", "یورو", AssetKind.CURRENCY, provider_key="price_eur", symbol="EUR"),
    Asset("gbp", "پوند انگلیس", AssetKind.CURRENCY, provider_key="price_gbp", symbol="GBP"),
    Asset("aed", "درهم امارات", AssetKind.CURRENCY, provider_key="price_aed", symbol="AED"),
    Asset("try", "لیر ترکیه", AssetKind.CURRENCY, provider_key="price_try", symbol="TRY"),
    Asset("cny", "یوان چین", AssetKind.CURRENCY, provider_key="price_cny", symbol="CNY"),
    # ------------------------------------------------------------- رمزارز
    Asset("bitcoin", "بیت‌کوین", AssetKind.CRYPTO, unit="usd", provider="coingecko",
          provider_key="bitcoin", symbol="BTC"),
    Asset("ethereum", "اتریوم", AssetKind.CRYPTO, unit="usd", provider="coingecko",
          provider_key="ethereum", symbol="ETH"),
    Asset("tether", "تتر", AssetKind.CRYPTO, unit="usd", precision=4, provider="coingecko",
          provider_key="tether", symbol="USDT"),
    Asset("binancecoin", "بایننس‌کوین", AssetKind.CRYPTO, unit="usd", precision=2,
          provider="coingecko", provider_key="binancecoin", symbol="BNB"),
    Asset("solana", "سولانا", AssetKind.CRYPTO, unit="usd", precision=2,
          provider="coingecko", provider_key="solana", symbol="SOL"),
    Asset("ripple", "ریپل", AssetKind.CRYPTO, unit="usd", precision=4,
          provider="coingecko", provider_key="ripple", symbol="XRP"),
    Asset("cardano", "کاردانو", AssetKind.CRYPTO, unit="usd", precision=4,
          provider="coingecko", provider_key="cardano", symbol="ADA"),
    Asset("dogecoin", "دوج‌کوین", AssetKind.CRYPTO, unit="usd", precision=5,
          provider="coingecko", provider_key="dogecoin", symbol="DOGE"),
)

ASSETS: dict[str, Asset] = {asset.slug: asset for asset in _ASSETS}

KIND_ORDER: tuple[AssetKind, ...] = (
    AssetKind.GOLD,
    AssetKind.COIN,
    AssetKind.CURRENCY,
    AssetKind.CRYPTO,
)

# اقلام شاخصی که در نمای کلی و فهرست پیش‌فرض نمایش داده می‌شوند
FEATURED: tuple[str, ...] = (
    "geram18",
    "sekee",
    "usd",
    "eur",
    "bitcoin",
    "ethereum",
)

# نام‌های جایگزین برای جستجو (فارسی محاوره‌ای و لاتین)
_ALIASES: dict[str, str] = {
    "طلا": "geram18",
    "طلای ۱۸": "geram18",
    "طلای ۱۸ عیار": "geram18",
    "طلای ۲۴": "geram24",
    "طلای ۲۴ عیار": "geram24",
    "مثقال": "mesghal",
    "سکه": "sekee",
    "سکه امام": "sekee",
    "امامی": "sekee",
    "بهار": "sekeb",
    "بهار ازادی": "sekeb",
    "نیم": "nim",
    "ربع": "rob",
    "گرمی": "gerami",
    "دلار": "usd",
    "دلار امریکا": "usd",
    "دلار آمریکا": "usd",
    "یورو": "eur",
    "یوان": "cny",
    "پوند": "gbp",
    "درهم": "aed",
    "لیر": "try",
    "بیت کوین": "bitcoin",
    "بیت‌کوین": "bitcoin",
    "btc": "bitcoin",
    "eth": "ethereum",
    "usdt": "tether",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "دوج": "dogecoin",
    "سولانا": "solana",
    "تتر": "tether",
    "ریپل": "ripple",
    "کاردانو": "cardano",
}


def normalize_query(text: str) -> str:
    """یکسان‌سازی متن جستجو (ی/ک عربی، نیم‌فاصله، ارقام)."""
    table = str.maketrans("يكﻰ٠١٢٣٤٥٦٧٨٩‌", "یکی۰۱۲۳۴۵۶۷۸۹ ")
    return " ".join((text or "").translate(table).strip().lower().split())


def exists(slug: str) -> bool:
    return slug in ASSETS


def get(slug: str) -> Asset:
    """قلم را برمی‌گرداند یا ``UnknownAsset`` می‌دهد."""
    asset = ASSETS.get(slug)
    if asset is None:
        raise UnknownAsset(slug)
    return asset


def by_kind(kind: AssetKind) -> list[Asset]:
    return [asset for asset in all_assets_ordered() if asset.kind is kind]


def all_assets_ordered() -> list[Asset]:
    """همهٔ اقلام به‌ترتیب دسته و سپس ترتیب تعریف."""
    return sorted(ASSETS.values(), key=lambda a: (a.kind.order, _INDEX[a.slug]))


def by_provider(name: str) -> list[Asset]:
    """اقلامی که از یک منبع خوانده می‌شوند — ورودی زنجیرهٔ جمع‌آوری."""
    return [asset for asset in all_assets_ordered() if asset.provider == name]


def search(query: str) -> Asset | None:
    """جستجوی نرم روی شناسه، عنوان، نماد و نام‌های جایگزین."""
    needle = normalize_query(query)
    if not needle:
        return None
    if needle in ASSETS:
        return ASSETS[needle]
    alias = _ALIASES.get(needle)
    if alias:
        return ASSETS.get(alias)
    for asset in all_assets_ordered():
        if needle == normalize_query(asset.title):
            return asset
    for asset in all_assets_ordered():
        if needle in normalize_query(asset.title) or needle == asset.symbol.lower():
            return asset
    for alias_key, slug in _ALIASES.items():
        if needle in normalize_query(alias_key):
            return ASSETS.get(slug)
    return None


_INDEX: dict[str, int] = {asset.slug: index for index, asset in enumerate(_ASSETS)}

ALL_ASSETS: tuple[Asset, ...] = _ASSETS

__all__ = [
    "ALL_ASSETS",
    "ASSETS",
    "FEATURED",
    "KIND_ORDER",
    "all_assets_ordered",
    "by_kind",
    "by_provider",
    "exists",
    "get",
    "normalize_query",
    "search",
]
