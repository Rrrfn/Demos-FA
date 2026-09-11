# -*- coding: utf-8 -*-
"""کیبوردهای inline — همه از رجیستری دارایی‌ها ساخته می‌شوند.

الگوی callback_data یکسان است: ``<scope>:<action>:<payload>`` تا هندلرها
بتوانند با یک پارسر مشترک کار کنند.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..core import assets as asset_registry
from ..core.models import AssetKind
from ..storage import Alert, AlertStatus

PER_ROW = 2


def main_menu() -> InlineKeyboardMarkup:
    """منوی اصلی."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 بازار", callback_data="nav:market"),
            InlineKeyboardButton(text="⭐ دیده‌بان", callback_data="nav:watchlist"),
        ],
        [
            InlineKeyboardButton(text="🥇 طلا و سکه", callback_data="nav:kind:gold"),
            InlineKeyboardButton(text="🪙 رمزارزها", callback_data="nav:kind:crypto"),
        ],
        [
            InlineKeyboardButton(text="🔔 هشدارها", callback_data="nav:alerts"),
            InlineKeyboardButton(text="🩺 وضعیت منابع", callback_data="nav:status"),
        ],
    ])


def _chunk(buttons: list[InlineKeyboardButton], per_row: int = PER_ROW) -> list[list[InlineKeyboardButton]]:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def assets_keyboard(
    slugs: list[str],
    *,
    action: str = "price",
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
    show_back: bool = True,
) -> InlineKeyboardMarkup:
    """کیبورد اقلام با اکشن مشخص (نمایش قیمت، افزودن به دیده‌بان، …)."""
    buttons = [
        InlineKeyboardButton(
            text=f"{asset_registry.ASSETS[slug].emoji} {asset_registry.ASSETS[slug].title}",
            callback_data=f"{action}:{slug}",
        )
        for slug in slugs
        if asset_registry.exists(slug)
    ]
    rows = _chunk(buttons)
    if extra_rows:
        rows.extend(extra_rows)
    if show_back:
        rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def market_keyboard() -> InlineKeyboardMarkup:
    """بازار: اقلام شاخص + دسته‌ها."""
    featured = [s for s in asset_registry.FEATURED]
    return assets_keyboard(
        featured,
        action="price",
        extra_rows=[
            [
                InlineKeyboardButton(text="🥇 طلا و سکه", callback_data="nav:kind:gold"),
                InlineKeyboardButton(text="💱 ارزها", callback_data="nav:kind:currency"),
            ],
            [
                InlineKeyboardButton(text="🪙 رمزارزها", callback_data="nav:kind:crypto"),
                InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="nav:market"),
            ],
        ],
        show_back=True,
    )


def kind_keyboard(kind: AssetKind) -> InlineKeyboardMarkup:
    """کیبورد یک دسته."""
    slugs = [a.slug for a in asset_registry.by_kind(kind)]
    return assets_keyboard(slugs, action="price")


def price_detail_keyboard(slug: str, *, in_watchlist: bool = False) -> InlineKeyboardMarkup:
    """اکشن‌های کنار یک قیمت."""
    watch_text = "⭐ حذف از دیده‌بان" if in_watchlist else "⭐ افزودن به دیده‌بان"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data=f"price:{slug}"),
            InlineKeyboardButton(text="📈 نمودار", callback_data=f"chart:{slug}"),
        ],
        [
            InlineKeyboardButton(text=watch_text, callback_data=f"watch:{slug}"),
            InlineKeyboardButton(text="🔔 هشدار", callback_data=f"alertnew:{slug}"),
        ],
        [InlineKeyboardButton(text="🔙 بازار", callback_data="nav:market")],
    ])


def alert_direction_keyboard(slug: str) -> InlineKeyboardMarkup:
    """انتخاب جهت شرط هشدار."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬆️ بالاتر از", callback_data=f"alertdir:above:{slug}"),
            InlineKeyboardButton(text="⬇️ پایین‌تر از", callback_data=f"alertdir:below:{slug}"),
        ],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="alertcancel")],
    ])


def alerts_keyboard(alerts: list[Alert]) -> InlineKeyboardMarkup:
    """مدیریت هشدارها: هر هشدار یک ردیف با خاموش/روشن و حذف."""
    rows: list[list[InlineKeyboardButton]] = []
    for alert in alerts[:10]:
        title = asset_registry.ASSETS[alert.slug].title if asset_registry.exists(alert.slug) else alert.slug
        toggle_text = "▶️ روشن" if alert.status is AlertStatus.PAUSED else "⏸ خاموش"
        rows.append([
            InlineKeyboardButton(
                text=f"{title} {alert.direction.label}",
                callback_data=f"alertinfo:{alert.id}",
            ),
            InlineKeyboardButton(text=toggle_text, callback_data=f"alerttoggle:{alert.id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"alertdel:{alert.id}"),
        ])
    rows.append([
        InlineKeyboardButton(text="➕ هشدار جدید", callback_data="nav:alertnew"),
        InlineKeyboardButton(text="📜 رویدادها", callback_data="nav:events"),
    ])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def watchlist_keyboard(slugs: list[str]) -> InlineKeyboardMarkup:
    """اقلام دیده‌بان با امکان حذف."""
    rows: list[list[InlineKeyboardButton]] = []
    for slug in slugs:
        if not asset_registry.exists(slug):
            continue
        asset = asset_registry.ASSETS[slug]
        rows.append([
            InlineKeyboardButton(text=f"📊 {asset.title}", callback_data=f"price:{slug}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"unwatch:{slug}"),
        ])
    rows.append([
        InlineKeyboardButton(text="➕ افزودن قلم", callback_data="nav:market"),
        InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="nav:watchlist"),
    ])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف", callback_data="alertcancel")]
    ])


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="nav:menu")]
    ])


__all__ = [
    "alert_direction_keyboard",
    "alerts_keyboard",
    "assets_keyboard",
    "back_to_menu",
    "cancel_keyboard",
    "kind_keyboard",
    "main_menu",
    "market_keyboard",
    "price_detail_keyboard",
    "watchlist_keyboard",
]
