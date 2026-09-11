# -*- coding: utf-8 -*-
"""پل بین پایشگر و تلگرام.

پایشگر فقط قرارداد ``Notifier`` را می‌شناسد؛ این کلاس جزئیات تلگرام را
پوشش می‌دهد. خطاهای گذرای شبکه یک‌بار دیگر تلاش می‌شوند و خطای نهایی
بالا می‌رود تا پایشگر آن را ثبت و در صورت تکرار هشدار را غیرفعال کند.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..core.errors import ProviderError
from ..core.models import Quote
from ..storage import Alert
from . import texts

log = logging.getLogger("ghematyar.notifier")


class TelegramNotifier:
    """ارسال اعلان هشدار به کاربر."""

    def __init__(self, bot: Bot, *, max_attempts: int = 2) -> None:
        self.bot = bot
        self.max_attempts = max(1, max_attempts)

    async def send(self, alert: Alert, quote: Quote) -> None:
        """ارسال پیام اعلان همراه کیبورد مدیریت."""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📜 رویدادها", callback_data="nav:events"),
            InlineKeyboardButton(text="🔔 هشدارها", callback_data="nav:alerts"),
        ]])
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                await self.bot.send_message(
                    chat_id=alert.user_id,
                    text=texts.render_alert_triggered(alert, quote),
                    reply_markup=keyboard,
                )
                return
            except TelegramRetryAfter as exc:
                # تلگرام خودش گفته چند ثانیه صبر کن
                wait = float(getattr(exc, "retry_after", 1) or 1)
                log.warning("telegram asked to retry after %.0fs", wait)
                await asyncio.sleep(wait)
                last_error = exc
            except TelegramForbiddenError as exc:
                # کاربر ربات را بلاک کرده؛ تلاش دوباره بی‌فایده است
                raise ProviderError("telegram", f"user blocked the bot: {exc}", retryable=False) from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("notify attempt %d/%d failed: %s", attempt, self.max_attempts, exc)
                if attempt < self.max_attempts:
                    await asyncio.sleep(1.5 * attempt)
        raise ProviderError("telegram", str(last_error))


__all__ = ["TelegramNotifier"]
