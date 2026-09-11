# -*- coding: utf-8 -*-
"""میان‌افزارها — ثبت کاربر، مهار سیل درخواست و گرفتن خطاها.

هیچ هندلری نباید خطای مدیریت‌نشده به کاربر نشان دهد یا ربات را از کار
بیندازد؛ این لایه آخرین سد است.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from ..core.errors import GhematyarError
from ..services import Services
from . import texts

log = logging.getLogger("ghematyar.middleware")

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


def _user_of(event: TelegramObject) -> User | None:
    return getattr(event, "from_user", None)


class UserTouchMiddleware(BaseMiddleware):
    """ثبت/به‌روزرسانی کاربر در هر تعامل (مبنای ترجیحات اعلان)."""

    def __init__(self, services: Services) -> None:
        self.services = services

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        user = _user_of(event)
        if user is not None and not user.is_bot:
            try:
                chat_id = getattr(getattr(event, "chat", None), "id", None)
                self.services.storage.users.touch(user.id, chat_id)
            except Exception as exc:  # noqa: BLE001
                # ثبت کاربر نباید مسیر اصلی را متوقف کند
                log.debug("user touch failed: %s", exc)
        return await handler(event, data)


class FloodMiddleware(BaseMiddleware):
    """مهار سیل سبک — محافظت از منابع داده و از خود کاربر.

    سقف عامدانه سخاوتمندانه است (کسی با استفادهٔ عادی به آن نمی‌خورد) و
    فقط جلوی حلقه‌های تکراری را می‌گیرد.
    """

    def __init__(self, *, max_events: int = 12, window: float = 10.0) -> None:
        self.max_events = max_events
        self.window = window
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._warned: dict[int, float] = {}

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        user = _user_of(event)
        if user is None:
            return await handler(event, data)
        now = time.monotonic()
        bucket = self._events[user.id]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.max_events:
            # حداکثر هر ۳۰ ثانیه یک‌بار هشدار می‌دهیم تا خودش سیل نشود
            if now - self._warned.get(user.id, 0.0) > 30:
                self._warned[user.id] = now
                message = (
                    "⏳ کمی آرام‌تر! تعداد درخواست‌ها زیاد شد.\n"
                    "چند لحظه صبر کنید و دوباره تلاش کنید."
                )
                if isinstance(event, Message):
                    await event.answer(message)
                elif isinstance(event, CallbackQuery):
                    await event.answer("کمی آرام‌تر لطفاً", show_alert=False)
            return None
        bucket.append(now)
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    """گرفتن خطاها و تبدیل آن‌ها به پیام قابل‌فهم."""

    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except GhematyarError as exc:
            log.warning("domain error in handler: %s", exc)
            await _reply(event, texts.render_error(str(exc)))
            return None
        except Exception as exc:  # noqa: BLE001
            log.exception("unhandled error in handler: %s", exc)
            await _reply(event, texts.render_error("خطای غیرمنتظره"))
            return None


async def _reply(event: TelegramObject, text: str) -> None:
    """پاسخ به پیام یا كالبک، بدون بالا بردن خطای تازه."""
    try:
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            if event.message is not None:
                await event.message.answer(text)
            else:
                await event.answer("خطا", show_alert=True)
    except Exception as exc:  # noqa: BLE001
        log.debug("could not deliver error message: %s", exc)


__all__ = ["ErrorMiddleware", "FloodMiddleware", "UserTouchMiddleware"]
