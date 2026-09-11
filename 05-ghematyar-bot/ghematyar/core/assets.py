# -*- coding: utf-8 -*-
"""فهرست دارایی‌ها — تک‌منبع حقیقت.

افزودن یک قلم جدید فقط یک ورودی در ``ASSETS`` است؛ ارائه‌دهنده‌ها،
کیبوردها، جست‌وجو و موتور هشدار همه از همین‌جا تغذیه می‌شوند.

هر قلم می‌تواند در چند منبع کلید داشته باشد. نبود کلید در یک منبع
یعنی «این منبع آن قلم را ندارد» — نه «قیمت صفر» و نه دادهٔ ساختگی.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import UnknownAsset
from .models import AssetKind


@dataclass(frozen=True, slots=True)
class Asset:
    """یک قلم قابل معامله/پایش."""

    slug: str
    title: str
    kind: AssetKind
    unit: str = "toman"                 # toman | usd
    emoji: str = "💠"
    precision: int = 0                  # تعداد رقم اعشار در نمایش
    # کلیدها در هر منبع
    tgju_ajax: tuple[str, ...] = ()
    tgju_html: tuple[str, ...] = ()
    coingecko: str = ""
    # جست‌وجو
    keywords: tuple[str, ...] = ()
    # در پیام‌های خلاصه نشان داده شود؟
    featured: bool = False

    @property
    def unit_label(self) -> str:
        return "دلار" if self.unit == "usd" else "تومان"

    @property
    def aliases(self) -> tuple[str, ...]:
        """همهٔ نام‌های قابل جست‌وجو."""
        return (self.title, self.slug, *self.keywords)

    def has_source(self, provider: str) -> bool:
        """آیا این قلم در منبع داده‌شده کلید دارد؟"""
        if provider == "tgju":
            return bool(self.tgju_ajax or self.tgju_html)
        if provider == "coingecko":
            return bool(self.coingecko)
        return False


# ---------------------------------------------------------------- gold
_GOLD = (
    Asset(
        slug="geram18", title="طلای ۱۸ عیار", kind=AssetKind.GOLD, emoji="🥇",
        tgju_ajax=("geram18",), tgju_html=("geram18",),
        keywords=("طلا", "طلای18", "طلای ۱۸", "گرم", "گرم طلا", "gold"),
        featured=True,
    ),
    Asset(
        slug="geram24", title="طلای ۲۴ عیار", kind=AssetKind.GOLD, emoji="🏅",
        tgju_ajax=("geram24",), tgju_html=("geram24",),
        keywords=("طلای24", "طلای ۲۴", "طلا ۲۴"),
    ),
    Asset(
        slug="mesghal", title="مثقال طلا", kind=AssetKind.GOLD, emoji="⚖️",
        tgju_ajax=("mesghal",), tgju_html=("mesghal",),
        keywords=("مثقال", "mesghal"),
    ),
)

# ---------------------------------------------------------------- coins
_COINS = (
    Asset(
        slug="sekee", title="سکه امامی", kind=AssetKind.COIN, emoji="🪙",
        tgju_ajax=("sekee",), tgju_html=("sekee",),
        keywords=("سکه", "امامی", "سکه امامی", "تمام", "تمام سکه"),
        featured=True,
    ),
    Asset(
        slug="sekeb", title="سکه بهار آزادی", kind=AssetKind.COIN, emoji="🥈",
        tgju_ajax=("sekeb",), tgju_html=("sekeb",),
        keywords=("بهار", "آزادی", "بهار آزادی"),
    ),
    Asset(
        slug="nim", title="نیم‌سکه", kind=AssetKind.COIN, emoji="🥉",
        tgju_ajax=("nim",), tgju_html=("nim",),
        keywords=("نیم", "نیم سکه", "نیم‌سکه"),
    ),
    Asset(
        slug="rob", title="ربع‌سکه", kind=AssetKind.COIN, emoji="🪙",
        tgju_ajax=("rob",), tgju_html=("rob",),
        keywords=("ربع", "ربع سکه", "ربع‌سکه"),
    ),
    # سکه گرمی در خوراک ماشین‌خوان tgju نیست و فقط از HTML درمی‌آید (کلید ``gerami``)؛
    # اگر آن مسیر داده ندهد، قلم صادقانه غایب می‌ماند (نه قیمت ساختگی).
    Asset(
        slug="gemi", title="سکه گرمی", kind=AssetKind.COIN, emoji="⚪",
        tgju_html=("gerami",),
        keywords=("گرمی", "سکه گرمی"),
    ),
)

# ---------------------------------------------------------------- currency
_CURRENCY = (
    Asset(
        slug="usd", title="دلار آمریکا", kind=AssetKind.CURRENCY, emoji="💵",
        tgju_ajax=("price_dollar_rl",), tgju_html=("price_dollar_rl",),
        keywords=("دلار", "دلار امریکا", "دلار آمریکا", "usd", "dollar"),
        featured=True,
    ),
    Asset(
        slug="eur", title="یورو", kind=AssetKind.CURRENCY, emoji="💶",
        tgju_ajax=("price_eur",), tgju_html=("price_eur",),
        keywords=("یورو", "eur", "euro"),
        featured=True,
    ),
    Asset(
        slug="gbp", title="پوند انگلیس", kind=AssetKind.CURRENCY, emoji="💷",
        tgju_ajax=("price_gbp",), tgju_html=("price_gbp",),
        keywords=("پوند", "پوند انگلیس", "gbp"),
    ),
    Asset(
        slug="aed", title="درهم امارات", kind=AssetKind.CURRENCY, emoji="🇦🇪",
        tgju_ajax=("price_aed",), tgju_html=("price_aed",),
        keywords=("درهم", "درهم امارات", "aed"),
    ),
    Asset(
        slug="try", title="لیر ترکیه", kind=AssetKind.CURRENCY, emoji="🇹🇷",
        tgju_ajax=("price_try",), tgju_html=("price_try",),
        keywords=("لیر", "لیر ترکیه", "try"),
    ),
    Asset(
        slug="cny", title="یوان چین", kind=AssetKind.CURRENCY, emoji="🇨🇳",
        tgju_ajax=("price_cny",), tgju_html=("price_cny",),
        keywords=("یوان", "یوان چین", "cny"),
    ),
)

# ---------------------------------------------------------------- crypto
_CRYPTO = (
    Asset(
        slug="bitcoin", title="بیت‌کوین", kind=AssetKind.CRYPTO, unit="usd", emoji="🟠",
        precision=2, coingecko="bitcoin", tgju_ajax=("crypto-bitcoin",),
        keywords=("بیت", "بیتکوین", "بیت کوین", "btc", "bitcoin"),
        featured=True,
    ),
    Asset(
        slug="ethereum", title="اتریوم", kind=AssetKind.CRYPTO, unit="usd", emoji="🔷",
        precision=2, coingecko="ethereum", tgju_ajax=("crypto-ethereum",),
        keywords=("اتریوم", "eth", "ethereum"),
        featured=True,
    ),
    Asset(
        slug="tether", title="تتر", kind=AssetKind.CRYPTO, unit="usd", emoji="💚",
        precision=4, coingecko="tether", tgju_ajax=("crypto-tether",),
        keywords=("تتر", "usdt", "tether"),
    ),
    Asset(
        slug="binancecoin", title="بایننس‌کوین", kind=AssetKind.CRYPTO, unit="usd",
        emoji="🟡", precision=2, coingecko="binancecoin", tgju_ajax=("crypto-binance-coin",),
        keywords=("بایننس", "بی‌ان‌بی", "bnb", "binance"),
    ),
    Asset(
        slug="solana", title="سولانا", kind=AssetKind.CRYPTO, unit="usd", emoji="🟣",
        precision=2, coingecko="solana", tgju_ajax=("crypto-solana",),
        keywords=("سولانا", "sol", "solana"),
    ),
    Asset(
        slug="ripple", title="ریپل", kind=AssetKind.CRYPTO, unit="usd", emoji="🔵",
        precision=4, coingecko="ripple", tgju_ajax=("crypto-ripple",),
        keywords=("ریپل", "xrp", "ripple"),
    ),
    Asset(
        slug="cardano", title="کاردانو", kind=AssetKind.CRYPTO, unit="usd", emoji="🔹",
        precision=4, coingecko="cardano", tgju_ajax=("crypto-cardano",),
        keywords=("کاردانو", "ada", "cardano"),
    ),
    Asset(
        slug="dogecoin", title="دوج‌کوین", kind=AssetKind.CRYPTO, unit="usd", emoji="🐕",
        precision=5, coingecko="dogecoin", tgju_ajax=("crypto-dogecoin",),
        keywords=("دوج", "دوجکوین", "doge", "dogecoin"),
    ),
    Asset(
        slug="tron", title="ترون", kind=AssetKind.CRYPTO, unit="usd", emoji="🔺",
        precision=5, coingecko="tron", tgju_ajax=("crypto-tron",),
        keywords=("ترون", "trx", "tron"),
    ),
    Asset(
        slug="toncoin", title="تون‌کوین", kind=AssetKind.CRYPTO, unit="usd", emoji="💎",
        precision=3, coingecko="the-open-network", tgju_ajax=("crypto-toncoin",),
        keywords=("تون", "تونکوین", "ton", "toncoin"),
    ),
    Asset(
        slug="usd_coin", title="یو‌اس‌دی‌کوین", kind=AssetKind.CRYPTO, unit="usd",
        emoji="🔒", precision=4, coingecko="usd-coin", tgju_ajax=("crypto-usd-coin",),
        keywords=("usdc", "یو اس دی کوین", "usd coin"),
    ),
)


ALL_ASSETS: tuple[Asset, ...] = _GOLD + _COINS + _CURRENCY + _CRYPTO

ASSETS: dict[str, Asset] = {a.slug: a for a in ALL_ASSETS}

# ترتیب نمایش گروه‌ها
KIND_ORDER: tuple[AssetKind, ...] = (
    AssetKind.GOLD,
    AssetKind.COIN,
    AssetKind.CURRENCY,
    AssetKind.CRYPTO,
)

FEATURED: tuple[str, ...] = tuple(a.slug for a in ALL_ASSETS if a.featured)


# ---------------------------------------------------------------- helpers
def all_assets_ordered() -> tuple[Asset, ...]:
    """همهٔ دارایی‌ها به ترتيب گروه (طلا، سکه، ارز، رمزارز)."""
    ordered: list[Asset] = []
    for kind in KIND_ORDER:
        ordered.extend(by_kind(kind))
    return tuple(ordered)


def by_kind(kind: AssetKind) -> tuple[Asset, ...]:
    """دارایی‌های یک دسته، به ترتیب فهرست."""
    return tuple(a for a in ALL_ASSETS if a.kind is kind)


def get(slug: str) -> Asset:
    """دارایی با slug — در نبودش خطای دامنه می‌دهد."""
    asset = ASSETS.get(slug)
    if asset is None:
        raise UnknownAsset(slug)
    return asset


def exists(slug: str) -> bool:
    return slug in ASSETS


def assets_with_source(provider: str) -> tuple[Asset, ...]:
    """دارایی‌هایی که یک منبع می‌تواند تأمین کند."""
    return tuple(a for a in ALL_ASSETS if a.has_source(provider))


_NORMALIZE_MAP = str.maketrans({
    "ي": "ی", "ك": "ک", "ۀ": "ه", "أ": "ا", "إ": "ا", "آ": "ا",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})


def normalize_query(text: str) -> str:
    """نرمال‌سازی متن جست‌وجو — یکسان‌سازی حروف و حذف فاصله‌ها."""
    out = (text or "").strip().translate(_NORMALIZE_MAP)
    out = out.replace("\u200c", "").replace(" ", "").replace("-", "").lower()
    return re.sub(r"[^\w\u0600-\u06ff]", "", out)


def search(query: str) -> Asset | None:
    """جست‌وجوی یک قلم با نام فارسی، slug یا کلیدواژه.

    تطبیق سه‌مرحله‌ای است: برابری کامل، سپس کلیدواژهٔ کامل، و در پایان
    «شامل بودن». طولانی‌ترین تطبیق برنده می‌شود تا «نیم‌سکه» به «سکه» نچسبد.
    """
    q = normalize_query(query)
    if not q:
        return None

    exact: Asset | None = None
    partial: list[tuple[int, Asset]] = []
    for asset in ALL_ASSETS:
        for alias in asset.aliases:
            a = normalize_query(alias)
            if not a:
                continue
            if a == q:
                exact = asset
                break
            if a in q or q in a:
                partial.append((len(a), asset))
        if exact is not None:
            break
    if exact is not None:
        return exact
    if not partial:
        return None
    partial.sort(key=lambda item: -item[0])
    return partial[0][1]
